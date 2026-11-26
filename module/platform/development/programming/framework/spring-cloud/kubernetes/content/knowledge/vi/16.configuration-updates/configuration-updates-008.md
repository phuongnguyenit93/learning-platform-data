# Xử lý nhiều thay đổi liên tiếp và tránh refresh quá mức

## Mục tiêu bài học

Trong chương **Cập nhật cấu hình** của module **SPRING_CLOUD_KUBERNETES**, việc nhận được thông báo ConfigMap hoặc Secret thay đổi mới chỉ là bước đầu. Khi nhiều thay đổi đến gần nhau, gọi refresh cho từng sự kiện có thể làm ứng dụng liên tục nạp lại nguồn, vô hiệu hóa bean và tạo lại tài nguyên.

Sau bài học, bạn có thể:

- Phân biệt trì hoãn, debounce, giới hạn tần suất, gom thay đổi và bỏ qua cấu hình không đổi.
- Thiết kế xử lý tuần tự mà vẫn giữ được thay đổi đến trong lúc refresh.
- Phân biệt sự kiện đã nhận, cấu hình mong muốn và cấu hình thực sự đã áp dụng.
- Xử lý lỗi, retry và nhiều replica mà không tạo thêm đợt refresh dồn dập.
- Xác định phần nào do Configuration Watcher cung cấp và phần nào cần tự tích hợp.

Mục tiêu vận hành là **hội tụ về cấu hình mong muốn hợp lệ với số lần áp dụng cần thiết**, đồng thời kiểm soát ảnh hưởng đến các yêu cầu đang phục vụ.

## 1. Vì sao một lần chỉnh cấu hình có thể tạo nhiều refresh?

Giả sử dịch vụ `orders` có ba thay đổi liên tiếp:

| Thời điểm minh họa | Thay đổi |
|---|---|
| 0 ms | Tăng timeout thanh toán |
| 400 ms | Điều chỉnh số lần thử lại |
| 900 ms | Sửa lại timeout sau khi kiểm tra |
| Sau đó | Một đường gửi thông báo thử lại vì chưa nhận được phản hồi |

Nếu mỗi thông báo lập tức kích hoạt refresh trên sáu Pod, ba thay đổi đã có thể tạo 18 lần thực thi refresh. Thông báo gửi lại hoặc hai đường kích hoạt độc lập có thể làm số lần gọi tăng thêm.

Các nguyên nhân thường gặp:

- Người vận hành chỉnh từng key thay vì công bố một bộ cấu hình hoàn chỉnh.
- Pipeline cập nhật nhiều ConfigMap/Secret liên quan theo từng thao tác.
- Nhiều thành phần cùng gửi refresh: watcher, pipeline và lời gọi quản trị thủ công.
- Một request timeout khiến bên gửi thử lại dù bên nhận có thể đã xử lý.
- Nhiều watcher replica cùng hoạt động khi chưa có cơ chế phối hợp phù hợp.
- Tài nguyên thay metadata, đồng bộ lại hoặc được quan sát lại dù dữ liệu nghiệp vụ không đổi.

Không cần kết luận Kubernetes watch luôn gửi trùng hay đảo thứ tự. Vấn đề là đường xử lý tổng thể có nhiều bước và không nên dựa vào giả định mỗi thay đổi chỉ dẫn tới đúng một lần áp dụng.

Trong Spring Cloud, refresh có thể tác động tới binding cấu hình và vòng đời bean trong refresh scope. Việc bean khởi tạo lại có thể diễn ra khi được sử dụng sau đó, nên chi phí không chỉ nằm trong thời gian trả lời HTTP của endpoint. Xem [Spring Cloud Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope).

## 2. Sự kiện là tín hiệu để kiểm tra lại trạng thái

Một sự kiện nói rằng “nguồn có thể đã thay đổi”. Nó không nhất thiết là một yêu cầu nghiệp vụ bắt buộc phải thực thi độc lập.

Ví dụ:

```text
Cấu hình đang dùng: A

Các bản được công bố nhanh: B -> C -> D

Chính sách hội tụ trạng thái:
  đọc lại trạng thái mong muốn và áp dụng D nếu D hợp lệ
```

Bỏ qua B và C có thể phù hợp khi đó chỉ là những giá trị timeout trung gian. Tuy nhiên, nếu mỗi bước là một hành động bắt buộc, như kích hoạt một quy trình thanh toán hay một migration, không được dùng ConfigMap rồi mong thuật toán gom sự kiện thực thi đầy đủ từng bước. Những hành động đó cần luồng công việc hoặc thông điệp có ngữ nghĩa riêng.

Cách suy nghĩ theo trạng thái mong muốn phù hợp với mô hình vòng lặp điều hòa của Kubernetes: quan sát, đối chiếu và đưa trạng thái hiện tại gần với trạng thái mong muốn. Xem [Kubernetes Controllers](https://kubernetes.io/docs/concepts/architecture/controller/).

Nên lưu ít nhất ba thông tin:

| Thông tin | Ý nghĩa |
|---|---|
| `observed` | Đã nhận tín hiệu hoặc quan sát nguồn |
| `desired` | Bộ cấu hình hiện muốn áp dụng |
| `applied` | Bộ cấu hình đã được áp dụng và xác minh theo tiêu chí của ứng dụng |

Nhận được sự kiện không được coi là đã áp dụng thành công. HTTP gửi refresh thành công cũng không tự chứng minh mọi client bên trong ứng dụng đã hoạt động với bản mới.

## 3. Phân biệt các cơ chế hạn chế refresh

| Cơ chế | Cách hoạt động | Giới hạn chính |
|---|---|---|
| Delay | Chờ một khoảng trước khi xử lý từng tín hiệu | Có thể vẫn xử lý đủ mọi tín hiệu |
| Debounce ở cuối đợt | Chờ nguồn yên trong một khoảng rồi xử lý | Thay đổi liên tục có thể làm chờ mãi |
| Giới hạn tần suất | Chặn các lần thực thi diễn ra quá gần nhau | Phải giữ lại công việc còn cần làm |
| Gom thay đổi | Nhiều tín hiệu cùng dẫn tới một lần đọc trạng thái mới nhất | Cần xác định đúng phạm vi gom |
| Bỏ qua bản không đổi | Không áp dụng nếu cấu hình hiệu lực bằng bản đang dùng | Phải so sánh đúng dữ liệu hiệu lực |
| Chỉ một lần đang chạy | Không chạy hai lần refresh đồng thời trong cùng phạm vi | Vẫn cần xử lý tín hiệu đến trong lúc chạy |

Các cơ chế bổ sung cho nhau. Chỉ khóa để hai refresh không chạy đồng thời vẫn có thể tạo một hàng dài các lần refresh tuần tự không cần thiết.

### Ví dụ với khoảng chờ 1,5 giây

Sự kiện đến tại `0`, `0,4` và `0,9` giây:

- Delay 1,5 giây cho từng sự kiện có thể tạo ba tác vụ tại `1,5`, `1,9` và `2,4` giây.
- Debounce ở cuối đợt dự kiến tạo một lượt xử lý tại `2,4` giây, nếu không có thay đổi mới.
- Giới hạn một lượt mỗi 5 giây cần giữ trạng thái còn chờ; không được đơn giản loại bỏ sự kiện cuối vì nó đến quá sớm.

Đây là minh họa thuật toán, không phải cam kết về thời điểm thực thi của scheduler hoặc một cấu hình mặc định của Spring.

## 4. Configuration Watcher không tự thay thế mọi cơ chế điều phối

Configuration Watcher có thể theo dõi ConfigMap/Secret được chọn và gửi thông báo refresh qua HTTP hoặc Spring Cloud Bus. Với HTTP, cần lưu ý việc nhắm tới các instance được phát hiện, thay vì chỉ một địa chỉ cân bằng tải.

Tài liệu cung cấp thuộc tính trì hoãn:

```yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
    value: "10000"
```

Giá trị ở đây tính theo mili giây và chỉ là ví dụ. Một mục đích quan trọng là chờ dữ liệu mount được kubelet cập nhật trước khi ứng dụng đọc lại. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Không suy ra từ thuộc tính này rằng thư viện bảo đảm:

- Gom mọi sự kiện gần nhau thành một refresh.
- Giới hạn số lần refresh trong một khoảng.
- Hủy tác vụ cũ khi có sự kiện mới.
- So sánh cấu hình hiệu lực trước khi vô hiệu hóa bean.
- Xác minh tất cả Pod đã áp dụng cùng phiên bản.

Các phần tiếp theo trình bày **thiết kế bộ điều phối bổ sung**. Những tên như `quietPeriod` và `minInterval` là tham số của thiết kế minh họa, không phải thuộc tính Spring Cloud Kubernetes được cung cấp sẵn.

Nếu dùng nguyên Configuration Watcher, trước hết hãy giảm nguồn phát thay đổi, chọn đúng tài nguyên cần theo dõi và đo số refresh thực tế. Chỉ xây thêm bộ điều phối khi nhu cầu vận hành đủ rõ.

## 5. Giảm số thay đổi ngay tại nơi công bố

Trước khi thêm timer và hàng đợi, giảm số lần ghi không cần thiết:

1. Chuẩn bị toàn bộ bộ cấu hình mới ở pipeline hoặc công cụ quản trị.
2. Kiểm tra cú pháp, kiểu dữ liệu, giới hạn và quan hệ giữa các trường.
3. Công bố một bộ dữ liệu hoàn chỉnh trong một lần cập nhật tài nguyên khi có thể.
4. Không liên tục ghi lại cùng dữ liệu chỉ để cập nhật dấu thời gian.
5. Tách cấu hình cần refresh khỏi metadata và cấu hình không liên quan.

Ví dụ một ConfigMap không nhạy cảm:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime
  namespace: shop
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: orders
data:
  app.release-id: "runtime-r7"
  app.checkout.timeout: "2500ms"
  app.checkout.max-attempts: "2"
```

Label chọn nguồn và annotation ánh xạ tới ứng dụng được mô tả trong [Monitoring ConfigMaps and Secrets](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html#monitoring-configmaps-and-secrets).

Một lần ghi ConfigMap không tạo giao dịch với Secret khác hoặc với backend. Nếu hai nguồn phải đi cùng nhau, cần một hợp đồng phiên bản, bản kê khai release hoặc cơ chế kiểm tra tính đầy đủ trước khi áp dụng.

Tránh đưa bí mật vào ConfigMap chỉ để gom mọi dữ liệu vào một đối tượng.

## 6. Chọn đúng khóa để gom công việc

Khóa gom thường phải phản ánh phạm vi cấu hình ảnh hưởng tới ứng dụng:

```text
Phạm vi điều phối tập trung:
  cluster + namespace + ứng dụng + profile/bộ nguồn

Phạm vi thực thi cục bộ:
  phạm vi cấu hình + định danh instance
```

Nếu `orders-runtime` và một Secret cùng ảnh hưởng tới một lần refresh của `orders`, chỉ gom theo tên tài nguyên có thể vẫn tạo hai refresh gần nhau. Ngược lại, gom mọi ứng dụng vào một khóa toàn cụm khiến thay đổi của dịch vụ A trì hoãn dịch vụ B.

Các trạng thái tối thiểu cho mỗi khóa:

| Trạng thái | Vai trò |
|---|---|
| Có thay đổi còn chờ | Biết cần đọc lại nguồn sau khi kết thúc lượt hiện tại |
| Thời điểm tín hiệu đầu/cuối của đợt chờ | Tính debounce và giới hạn chờ |
| Số thứ tự tín hiệu nội bộ | Phát hiện thay đổi đến trong lúc xử lý |
| Đang chạy | Bảo đảm một lượt thực thi trong phạm vi đó |
| Thời điểm bắt đầu lần gần nhất | Giới hạn tần suất |
| Bản áp dụng thành công gần nhất | Bỏ qua cấu hình không đổi |
| Thời điểm retry tiếp theo và ngân sách lỗi | Tránh thử lại dồn dập |

Số thứ tự nội bộ chỉ phục vụ đồng bộ bộ điều phối. Nó không phải `metadata.generation` hay `resourceVersion` của Kubernetes.

Chỉ nhận các khóa nằm trong phạm vi cho phép và dọn trạng thái đã hết sử dụng. Không tạo hàng đợi không giới hạn theo mọi tên do một request gửi đến.

## 7. Debounce phải giữ được thay đổi cuối cùng

### 7.1. Tham số minh họa

Giả sử bộ điều phối tự xây dùng:

```yaml
# Chỉ là cấu hình thiết kế minh họa của bộ điều phối tự xây.
quietPeriod: 1500ms
maxCoalesceWait: 10s
minIntervalBetweenStarts: 5s
maxConcurrentPerKey: 1
```

Ý nghĩa:

- `quietPeriod`: muốn chờ nguồn yên đủ lâu trước khi bắt đầu.
- `maxCoalesceWait`: giới hạn thời gian bị đẩy lùi chỉ vì tiếp tục gom tín hiệu.
- `minIntervalBetweenStarts`: khoảng tối thiểu giữa hai lần bắt đầu xử lý cùng khóa.
- `maxConcurrentPerKey`: chỉ một lượt chạy tại một thời điểm.

Một thời điểm đủ điều kiện xử lý có thể được tính như sau:

```text
coalesceDue = min(lastSignalAt + quietPeriod,
                  firstPendingSignalAt + maxCoalesceWait)

eligibleAt = max(coalesceDue,
                 lastStartAt + minIntervalBetweenStarts,
                 retryNotBefore)
```

`maxCoalesceWait` chỉ chặn việc trì hoãn vô hạn do debounce. Nó không phải thời hạn hoàn tất khi lượt trước còn chạy, nguồn chưa sẵn sàng, retry đang backoff hoặc bộ giới hạn tần suất chưa cho phép.

Dùng đồng hồ đơn điệu để tính khoảng thời gian trong một tiến trình, tránh sai lệch khi đồng hồ hệ thống được điều chỉnh.

### 7.2. Timeline minh họa

Giả định scheduler chạy kịp, nguồn có thể đọc và chưa có ràng buộc từ lượt trước:

| Thời điểm | Sự kiện | Trạng thái mong đợi |
|---|---|---|
| 0,0 s | B tới | Đánh dấu còn chờ |
| 0,4 s | C tới | Dời thời điểm xử lý theo debounce |
| 0,9 s | D tới | Dự kiến bắt đầu ở 2,4 s |
| 2,4 s | Bắt đầu lượt 1 | Đọc trạng thái nguồn hiện tại |
| 2,7 s | E tới khi lượt 1 đang chạy | Giữ dấu hiệu còn chờ; không chạy chồng |
| 3,2 s | Lượt 1 kết thúc | Còn việc cần kiểm tra lại |
| 7,4 s trở đi | Lượt 2 đủ khoảng cách giữa hai lần bắt đầu | Đọc lại nguồn, áp dụng E nếu khác bản đang dùng |

Nếu lượt 1 đã đọc được E và áp dụng E thành công, lượt 2 có thể kết thúc ở bước so sánh mà không cần thực hiện refresh nặng. Việc có thêm một lượt đối chiếu không đồng nghĩa phải có thêm một lần tạo lại bean.

### 7.3. Không được bỏ tín hiệu chỉ vì đang chạy

Một cách làm sai:

```text
nếu đang refresh:
    bỏ qua sự kiện mới
```

Giả sử lượt đang chạy đã đọc D, sau đó E được công bố. Bỏ sự kiện E có thể khiến ứng dụng giữ D cho đến khi có một thay đổi khác tình cờ đánh thức nó.

Cách phù hợp là ghi nhận `pending` hoặc tăng số thứ tự tín hiệu, rồi bảo đảm có lượt đối chiếu tiếp theo sau khi lượt hiện tại kết thúc.

## 8. Thuật toán điều phối tuần tự

Mã giả sau diễn tả nguyên tắc đồng bộ, không phải một lớp Spring có thể sao chép để sử dụng ngay:

```text
Khi nhận tín hiệu cho một khóa:
    trong vùng đồng bộ ngắn:
        tăng signalSequence
        đánh dấu pending
        ghi nhận thời điểm đầu/cuối của đợt chờ
        nếu chưa có lượt chạy:
            đặt lại duy nhất một lịch đánh thức theo chính sách

Khi lịch đánh thức có hiệu lực:
    trong vùng đồng bộ ngắn:
        bỏ qua callback đã lỗi thời
        nếu đang chạy hoặc không còn pending:
            kết thúc callback
        nếu chưa tới eligibleAt:
            đặt lịch lại
            kết thúc callback
        đánh dấu running
        tiêu thụ đợt pending hiện tại
        lưu sequenceAtStart
        ghi nhận lastStartAt

    ngoài vùng đồng bộ:
        đọc lại bộ nguồn mong muốn
        kiểm tra đầy đủ, parse và validate
        tính định danh cấu hình hiệu lực
        nếu bằng bản áp dụng thành công hiện tại:
            ghi nhận no-op
        nếu khác:
            áp dụng theo cơ chế đã tích hợp
            xác minh kết quả
            chỉ ghi nhận applied khi đủ điều kiện thành công
        phân loại lỗi nếu có

    trong finally và vùng đồng bộ ngắn:
        xóa trạng thái running
        giữ mọi pending được tạo trong lúc lượt chạy
        nếu sequence hiện tại khác sequenceAtStart:
            bảo đảm còn một lượt đối chiếu
        nếu lỗi có thể retry:
            giữ công việc và đặt retryNotBefore
        nếu còn công việc:
            đặt duy nhất một lịch tiếp theo
```

Những yêu cầu triển khai quan trọng:

- Không giữ khóa đồng bộ khi gọi API, đọc file, gọi HTTP refresh hoặc chờ kiểm tra sức khỏe.
- Hủy timer cũ chưa chắc ngăn callback đã bắt đầu; dùng mã thế hệ timer hoặc kiểm tra hạn hiện tại dưới cùng cơ chế đồng bộ.
- Sự kiện đến sau bước kiểm tra cuối phải vẫn nhìn thấy trạng thái và có thể đặt lịch mới.
- Mỗi khóa chỉ cần trạng thái “còn việc cần kiểm tra”, không cần giữ mọi sự kiện trung gian trong một hàng dài.
- Có timeout cho các thao tác bên ngoài; không để một lượt bị treo giữ khóa công việc mãi.
- Nếu timeout không thực sự dừng tác vụ, không khởi động lượt áp dụng khác chạy chồng lên tác vụ vẫn còn hoạt động.

Tại thời điểm khởi động bộ điều phối và sau khi phục hồi kết nối, nên đối chiếu nguồn hiện tại thay vì chỉ chờ một sự kiện mới. Kubernetes mô tả cơ chế list/watch và cách phục hồi khi lịch sử watch không còn trong [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/).

## 9. Bỏ qua cấu hình không đổi bằng dữ liệu hiệu lực

### 9.1. Đừng dùng mọi thay đổi metadata làm lý do refresh

`resourceVersion` thay đổi cho biết phiên bản tài nguyên đã thay đổi; nó không phải kết luận rằng timeout hiệu lực của ứng dụng đã khác.

Một định danh cấu hình hiệu lực nên xét:

- Các key ứng dụng thực sự dùng, bao gồm việc key bị xóa.
- Cách parse và chuẩn hóa kiểu dữ liệu.
- Thứ tự nguồn và độ ưu tiên ghi đè.
- Profile đang hoạt động và phiên bản schema cấu hình.
- Phiên bản bí mật hoặc tín hiệu thay đổi bí mật theo cách bảo vệ được dữ liệu.

Ví dụ `2500ms` và `2.5s` có thể được coi là tương đương nếu bộ parse của ứng dụng chuẩn hóa chúng thành cùng một Duration. Ngược lại, đảo thứ tự ưu tiên của hai nguồn có thể làm giá trị hiệu lực khác dù tập key trông giống nhau.

Không lấy hash trực tiếp của toàn bộ YAML gồm annotation thời gian rồi coi đó là cấu hình nghiệp vụ. Cũng không bỏ qua một trường có ảnh hưởng chỉ vì trường đó nằm ngoài danh sách key đã được viết thiếu.

### 9.2. So với bản đang áp dụng, không so với toàn bộ lịch sử đã từng thấy

Với chuỗi `A -> B -> A`, lần A cuối có thể chính là một rollback hợp lệ. Nếu chỉ ghi “A đã từng được xử lý” rồi loại bỏ, ứng dụng sẽ tiếp tục giữ B.

Điều kiện bỏ qua thường là:

```text
candidateFingerprint == lastSuccessfullyAppliedFingerprint
```

không phải:

```text
candidateFingerprint nằm trong tập mọi fingerprint từng xuất hiện
```

Nếu hệ thống ngoài đã thu hồi credential hoặc đổi hợp đồng, dữ liệu giống nhau cũng chưa chắc bảo đảm hành vi giống nhau. Tiêu chí xác minh phải phản ánh loại cấu hình đang quản lý.

### 9.3. Không so phiên bản của hai nguồn để suy ra một release

Không so `resourceVersion` của ConfigMap với Secret để kết luận hai nguồn thuộc cùng bộ cấu hình hoặc nguồn nào là “release mới hơn”. Dùng định danh release và quan hệ phiên bản được thiết kế rõ ràng.

Không giả định `metadata.generation` luôn tăng theo mọi thay đổi dữ liệu ConfigMap/Secret. Nếu cần số phiên bản nghiệp vụ, hãy định nghĩa và kiểm soát nó trong quy trình công bố.

Không đưa nội dung Secret hoặc hash dễ dò của mật khẩu vào log hay nhãn metric. Dùng định danh phiên bản không nhạy cảm được phép công bố.

## 10. Chờ dữ liệu sẵn sàng mà không nhầm với debounce

Với nguồn mount volume, sự kiện ở API có thể tới trước lúc file trong Pod đổi. Vì vậy, sau thời gian debounce, bộ đọc vẫn có thể nhìn thấy bản cũ.

Cần phân biệt:

| Câu hỏi | Cơ chế xử lý |
|---|---|
| Nguồn còn đang thay đổi dồn dập không? | Debounce và giới hạn chờ gom |
| Có đang thực thi quá thường xuyên không? | Giới hạn tần suất |
| File hoặc bộ nguồn đã tới bản cần dùng chưa? | Kiểm tra phiên bản và retry có giới hạn |
| Bean/tài nguyên đã dùng bản mới chưa? | Áp dụng và xác minh hành vi |

Kubernetes cập nhật ConfigMap mount theo cơ chế có độ trễ; env trong tiến trình đang chạy và mount `subPath` có các giới hạn khác. Xem [cơ chế cập nhật ConfigMap mount](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Đối với một bộ nhiều nguồn, có thể công bố một bản kê khai không nhạy cảm mô tả các phiên bản cần có. Bộ điều phối chỉ áp dụng khi đọc được tổ hợp đầy đủ theo hợp đồng đó.

Một nhãn release đơn lẻ xuất hiện trước các nguồn còn lại không phải bằng chứng bộ dữ liệu đã đầy đủ. Với Secret, kiểm tra qua định danh phiên bản hoặc phép thử được bảo vệ, không xuất giá trị để đối chiếu.

Nếu cơ chế đọc không thể cung cấp snapshot đủ nhất quán hoặc đối tượng không hỗ trợ đổi an toàn lúc chạy, dùng rollout với nguồn có phiên bản rõ ràng thường dễ kiểm soát hơn.

## 11. Lỗi, retry và cấu hình không hợp lệ

| Loại kết quả | Hướng xử lý |
|---|---|
| Dữ liệu giống bản đang dùng | Kết thúc no-op, không refresh nặng |
| Parse hoặc validate thất bại | Ghi nhận bản bị từ chối; chờ dữ liệu mới hoặc quy trình sửa |
| Mất kết nối tạm thời | Retry có backoff, jitter và ngân sách |
| File chưa tới phiên bản mong muốn | Đối chiếu lại sau khoảng chờ có giới hạn |
| Chưa đủ bộ ConfigMap/Secret | Giữ trạng thái chờ, báo độ trễ nếu vượt ngưỡng |
| Refresh đã chạy nhưng xác minh thất bại | Đánh giá trạng thái áp dụng một phần; không ghi nhận thành công |
| Lỗi quyền truy cập | Sửa danh tính/RBAC hoặc cấu hình đích, tránh retry liên tục |

Một chính sách retry minh họa có thể tăng khoảng đợi từ `1s`, `2s`, `4s` đến một trần, có thêm độ lệch ngẫu nhiên và một ngân sách thời gian. Đây là ví dụ thiết kế, cần điều chỉnh theo yêu cầu hội tụ và chi phí thực tế.

Các nguyên tắc:

- Không reset toàn bộ backoff chỉ vì một thông báo trùng tới.
- Khi có bản mới, đọc lại trạng thái mong muốn; tránh hàng đợi retry chứa nhiều payload cũ.
- Bản sai cú pháp xác định không nên bị parse và refresh lại dồn dập khi dữ liệu vẫn y nguyên.
- Hết ngân sách phải có trạng thái cần chú ý và đường phục hồi: bản mới, thao tác điều hòa được phép hoặc chu kỳ đối chiếu có kiểm soát.
- Dừng retry không có nghĩa coi bản cũ là bản mong muốn đã áp dụng.

Với Spring context refresh, không mặc định “lỗi thì mọi thứ tự quay về bản cũ”. Một số binding hoặc tài nguyên có thể đã đổi trước khi bước khác thất bại. Nếu cần công bố snapshot nguyên tử, phải xây cơ chế phù hợp cho nhóm cấu hình đó; một lời gọi refresh tổng quát không tự tạo giao dịch rollback.

## 12. Nhiều replica: gom sự kiện nhưng vẫn cập nhật mọi instance cần thiết

Giả sử sáu Pod cùng phục vụ `orders`. Một lần gom thay đổi ở tầng điều phối có thể tạo **một đợt phân phối**, nhưng vẫn có sáu instance cần được đối chiếu hoặc refresh.

Không đặt một distributed lock bao quanh thao tác refresh rồi cho chỉ một Pod thắng khóa là xong. Khi đó năm Pod còn lại có thể giữ cấu hình cũ.

Phân biệt hai phạm vi:

- **Phối hợp watcher:** tránh nhiều bộ phát cùng tạo một đợt thông báo trùng.
- **Thực thi trên instance:** bảo đảm từng Pod cần thiết hội tụ và không chạy chồng refresh trong chính Pod đó.

Tính năng HA/leader election của watcher phụ thuộc phiên bản và cấu hình triển khai; không suy rằng chỉ tăng replica là tự có đúng một bộ phát. Đối chiếu tài liệu tương ứng với release train đang dùng.

Một bảng theo dõi phù hợp:

| Instance | Desired | Applied | Trạng thái |
|---|---|---|---|
| orders-a | runtime-r7 | runtime-r7 | Đã xác minh |
| orders-b | runtime-r7 | runtime-r7 | Đã xác minh |
| orders-c | runtime-r7 | runtime-r6 | Chờ retry |
| orders-d mới tạo | runtime-r7 | Đang khởi động | Đọc nguồn lúc khởi động |

Không retry lại mọi Pod đã thành công chỉ vì một Pod chưa hội tụ. Nếu cần chia đợt hoặc thêm jitter để giảm tải backend, phải giữ khả năng kiểm tra từng instance và một mục tiêu hội tụ rõ ràng.

Spring Cloud LoadBalancer chọn đích cho một lời gọi; nó không tự bảo đảm một request gửi qua Service đã đến tất cả replica. Configuration Watcher có cơ chế phát hiện instance phục vụ việc nhắm đích, nhưng kết quả áp dụng vẫn cần được quan sát.

Nếu đang đồng thời dùng HTTP watcher, Bus và pipeline gọi refresh, cần chỉ rõ đường nào chịu trách nhiệm phát. Việc thêm một lớp gom cục bộ không tự vô hiệu hóa các đường đi vòng qua lớp đó.

## 13. Điểm tích hợp phải thực sự nằm trên đường refresh

Có hai vị trí thường được chọn cho bộ điều phối tự xây:

| Vị trí | Lợi ích | Việc phải làm rõ |
|---|---|---|
| Trước khi phân phối thông báo | Gom thay đổi theo ứng dụng, giảm số đợt fan-out | Theo dõi từng instance và phục hồi khi gửi thất bại |
| Tại ứng dụng nhận tín hiệu | Tuần tự hóa thực thi trong từng instance | Mọi đường kích hoạt cần đi qua điểm nhận được tích hợp |

Chỉ thêm một bean “debounce” vào ứng dụng không khiến request đang gửi thẳng tới `/actuator/refresh` tự đi qua bean đó. Phải có điểm tích hợp được thiết kế: bộ gửi thay thế, adapter hoặc điểm nhận tùy chỉnh phù hợp với đường thông báo đang sử dụng.

Tương tự, một bộ lọc HTTP chỉ chặn các request quá gần nhau rồi trả thành công có thể làm mất thay đổi cuối. Nếu không nhận xử lý ngay, điểm nhận vẫn phải lưu công việc còn chờ hoặc thông báo rõ để bên gửi có thể phục hồi.

Không dùng trường hợp HTTP timeout làm bằng chứng chắc chắn rằng server chưa refresh. Kiểm tra định danh đã áp dụng trước khi gửi lại thao tác có chi phí lớn.

Endpoint quản trị phải được bảo vệ và giới hạn trong phạm vi gọi cần thiết. RBAC của watcher cũng phải phù hợp với nguồn theo dõi; mở rộng quyền không phải cách sửa lỗi debounce hay cập nhật chồng nhau.

## 14. Thực hành tạo một đợt thay đổi liên tiếp

### 14.1. Điều kiện

Thực hành trong namespace lab `shop` với dữ liệu không nhạy cảm:

- Ứng dụng `orders` đang hoạt động và thực sự dùng các thuộc tính timeout/số lần thử lại.
- Nguồn `orders-runtime` đã được cấu hình cho ứng dụng; tên ứng dụng và nguồn thông báo được ánh xạ đúng.
- Có log hoặc endpoint nội bộ được bảo vệ cho biết release đang áp dụng và kết quả refresh.
- Muốn kiểm chứng thuật toán gom ở trên thì bộ điều phối phải đã được tích hợp trên đúng đường xử lý.

Nếu chỉ dùng watcher nguyên bản, bài thực hành vẫn giúp đo hành vi thực tế, nhưng không được kỳ vọng tự có debounce hoặc tự có đúng một lần refresh.

Cách import và chọn nguồn API cần đối chiếu [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html) và [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html). Đây là bước cấu hình của ứng dụng, không được tự suy từ label của watcher.

### 14.2. Công bố ba bản gần nhau bằng PowerShell

Đoạn lệnh dưới đây giữ label và annotation chọn nguồn trong mỗi manifest. Nó không ghi file trung gian:

```powershell
$changes = @(
    @{ Release = 'runtime-r8'; Timeout = '2500ms'; Attempts = '2' },
    @{ Release = 'runtime-r9'; Timeout = '2500ms'; Attempts = '3' },
    @{ Release = 'runtime-r10'; Timeout = '3s'; Attempts = '3' }
)

foreach ($change in $changes) {
    $manifest = @"
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime
  namespace: shop
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: orders
data:
  app.release-id: "$($change.Release)"
  app.checkout.timeout: "$($change.Timeout)"
  app.checkout.max-attempts: "$($change.Attempts)"
"@
    $manifest | kubectl apply -f -
    if ($LASTEXITCODE -ne 0) {
        throw 'Khong cong bo duoc ban cau hinh lab.'
    }
    Start-Sleep -Milliseconds 300
}
```

Khoảng 300 ms là khoảng nghỉ giữa các lệnh; thời điểm thực tế còn phụ thuộc thời gian gọi API. Muốn đối chiếu timeline, ghi nhận thời gian API chấp nhận từng bản thay vì giả định các sự kiện cách nhau chính xác 300 ms.

### 14.3. Quan sát kết quả

Có thể đọc nguồn và log được phép công bố:

```bash
kubectl get configmap orders-runtime -n shop
kubectl get pods -n shop -l app.kubernetes.io/name=orders
kubectl logs -n shop -l app.kubernetes.io/name=orders --prefix=true --tail=100
```

Selector trong lệnh phải khớp label Pod thực tế. Nếu nhiều replica hoặc giới hạn log làm thiếu dữ liệu, chọn từng Pod để kiểm tra.

Với bộ điều phối đã tích hợp, kiểm tra:

- Sau khi nguồn ổn định và hết các khoảng chờ, mỗi instance cần thiết hội tụ về `runtime-r10`.
- Trong một instance không có hai lượt áp dụng đang chạy chồng.
- Các bản trung gian có thể được gom; không bắt buộc luôn có đúng một lần áp dụng nếu nguồn chưa sẵn sàng hoặc đã bắt đầu xử lý trước đó.
- Thêm một thay đổi trong lúc refresh vẫn dẫn tới lượt đối chiếu tiếp theo.
- Một thông báo lặp với dữ liệu hiệu lực không đổi có thể trở thành no-op.
- Chuỗi A, B, A vẫn áp dụng được lần A cuối.
- Cấu hình sai bị từ chối rõ ràng và bản hợp lệ tiếp theo vẫn phục hồi được.

Đừng dùng số sự kiện giảm làm tiêu chí duy nhất. Một hệ thống không refresh lần nào vì đã làm mất tín hiệu cũng có số thực thi thấp, nhưng không đạt mục tiêu.

## 15. Đo lường để điều chỉnh chính sách

Các tên metric dưới đây là gợi ý cho bộ điều phối tự xây, không phải danh sách metric mặc định của Spring:

| Metric minh họa | Câu hỏi được trả lời |
|---|---|
| `config_signals_total` | Có bao nhiêu tín hiệu đầu vào? |
| `config_reconcile_total` | Có bao nhiêu lượt đọc và đối chiếu? |
| `config_apply_total` theo kết quả | Bao nhiêu lần áp dụng thành công/thất bại? |
| `config_noop_total` | Bao nhiêu lượt không cần áp dụng? |
| `config_pending` | Còn công việc chờ không? |
| `config_apply_inflight` | Có chạy chồng trong cùng phạm vi không? |
| `config_pending_age_seconds` | Công việc cũ nhất đang chờ bao lâu? |
| `config_apply_duration_seconds` | Chi phí áp dụng thực tế là bao nhiêu? |

Đối chiếu số lượt đọc, số lần refresh và độ trễ hội tụ. Nhiều lượt đối chiếu nhẹ nhưng ít lần refresh nặng có thể là kết quả phù hợp.

Không đưa mỗi release ID hoặc fingerprint vào label metric vì số lượng giá trị có thể tăng mãi. Giữ label theo các chiều có giới hạn; ghi định danh chi tiết ở log hoặc trạng thái nội bộ được bảo vệ.

Log hữu ích có thể nêu:

```text
app=orders instance=orders-a
desired=runtime-r10 applied=runtime-r9
result=pending reason=minimum-interval
```

Không ghi nội dung Secret. Thiết lập cảnh báo khi công việc chờ quá lâu, lỗi lặp lại, nhiều instance chưa hội tụ hoặc tốc độ refresh tăng bất thường.

## 16. Điều kiện để chính sách gom thay đổi vận hành đúng

Một chính sách hoàn chỉnh cần thỏa mãn:

- Sự kiện chỉ đánh thức việc đối chiếu, không ép phải áp dụng mọi bản trung gian.
- Có giới hạn tần suất và thời gian gom phù hợp với yêu cầu hội tụ.
- Có tối đa một lượt áp dụng đang chạy trong cùng phạm vi.
- Tín hiệu đến khi đang chạy được giữ lại.
- So sánh với cấu hình áp dụng thành công hiện tại, hỗ trợ cả rollback.
- Retry có giới hạn, phân loại lỗi và đường phục hồi.
- Mọi instance cần thiết đều được kiểm tra, kể cả instance mới.
- Điểm điều phối thực sự nằm trên các đường kích hoạt refresh.
- Có bằng chứng ứng dụng đã dùng cấu hình mới, thay vì chỉ đếm HTTP thành công.

Khi các điều kiện này không thể bảo đảm cho một loại cấu hình, chọn rollout có kiểm soát với nguồn được định danh rõ ràng. Giảm refresh quá mức chỉ có ý nghĩa khi ứng dụng vẫn áp dụng được bản cấu hình mong muốn một cách quan sát và kiểm chứng được.
