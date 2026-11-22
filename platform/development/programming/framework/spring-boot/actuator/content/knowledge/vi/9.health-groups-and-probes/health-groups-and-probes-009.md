# Vì sao kiểm tra phụ thuộc ngoài cần được cân nhắc khác nhau cho liveness và readiness

Một ứng dụng có thể vẫn chạy bình thường trong JVM nhưng tạm thời không hoàn thành được yêu cầu vì cơ sở dữ liệu bị mất kết nối. Nếu coi hai tình trạng này là một, hệ thống điều phối có thể khởi động lại hàng loạt ứng dụng trong khi nơi cần được khắc phục thực sự là cơ sở dữ liệu.

Muốn chọn đúng kiểm tra sức khỏe, hãy bắt đầu từ **hành động sẽ xảy ra sau khi kiểm tra thất bại**:

- **Liveness** phục vụ quyết định có cần khởi động lại container hay không.
- **Readiness** phục vụ quyết định có nên chuyển yêu cầu mới tới bản sao này hay không.
- **Giám sát phụ thuộc** cho biết cơ sở dữ liệu, bộ nhớ đệm hoặc dịch vụ khác đang gặp vấn đề để vận hành chẩn đoán và cảnh báo.

Ba mục đích này có thể dùng chung một số dữ liệu quan sát, nhưng không nên tự động dùng chung một điều kiện thành công.

## 1. Hai câu hỏi khác nhau dẫn tới hai cách xử lý khác nhau

Một **bản sao** là một phiên bản ứng dụng đang chạy, chẳng hạn một Pod trong nhóm ba Pod cùng phục vụ một Kubernetes Service. **Phụ thuộc ngoài** là tài nguyên nằm ngoài tiến trình ứng dụng: cơ sở dữ liệu, Redis, hệ thống nhắn tin, dịch vụ thanh toán hoặc API của đối tác.

| Khía cạnh | Liveness | Readiness |
| --- | --- | --- |
| Câu hỏi thiết kế | Trạng thái nội bộ đã hỏng tới mức cần khởi động lại chưa? | Bản sao này hiện có nên nhận yêu cầu mới không? |
| Phạm vi cần quan sát | Khả năng hoạt động và tự phục hồi của chính ứng dụng | Khả năng đáp ứng hợp đồng phục vụ của bản sao |
| Khi thất bại | Có thể dẫn tới khởi động lại container | Bản sao bị loại khỏi các đích nhận lưu lượng thông thường của Service |
| Phụ thuộc ngoài | Không đưa trực tiếp lỗi của hệ thống ngoài vào tiêu chí sống còn | Chỉ đưa vào sau khi phân tích tính thiết yếu và phạm vi lỗi |
| Ví dụ | Trạng thái nội bộ bị hỏng không thể tự phục hồi | Một bản sao chưa thể dùng tài nguyên bắt buộc để phục vụ |

Kubernetes áp dụng kết quả probe theo các ngưỡng đã cấu hình; một lần HTTP lỗi không đồng nghĩa container bị khởi động lại ngay. Readiness thất bại tự nó không phải lệnh khởi động lại. Xem [cơ chế các loại probe của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Trong Spring Boot, trạng thái khả dụng nội bộ được biểu diễn bằng `LivenessState` và `ReadinessState`. Đây là tín hiệu của ứng dụng, không phải cam kết rằng mọi luồng đều không bị kẹt hoặc mọi giao dịch đều sẽ thành công. Cơ chế này được mô tả trong [Application Availability của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

## 2. Vì sao lỗi phụ thuộc ngoài thường không thuộc liveness?

Giả sử ba bản sao `orders-a`, `orders-b` và `orders-c` cùng dùng cơ sở dữ liệu `orders-db`. Cơ sở dữ liệu tạm ngừng hoạt động trong một phút.

Nếu thiết kế liveness bằng điều kiện “truy vấn cơ sở dữ liệu thành công”, cả ba bản sao cùng thất bại:

~~~text
orders-db gặp lỗi
    -> cả ba bản sao báo liveness thất bại
    -> các container bị khởi động lại
    -> các bản sao tạo lại kết nối và nạp lại dữ liệu
    -> orders-db vẫn chưa hoạt động
    -> liveness tiếp tục thất bại
~~~

**Khởi động lại tiến trình orders không sửa được orders-db.** Với giả định nguyên nhân lỗi hoàn toàn nằm ở cơ sở dữ liệu, hành động phục hồi được chọn không tác động tới nguyên nhân.

Thậm chí việc khởi động lại có thể gây thêm chi phí:

- Mất các dữ liệu đã làm nóng trong bộ nhớ của từng tiến trình.
- Hủy công việc đang xử lý hoặc làm phức tạp việc thử lại.
- Tạo đợt kết nối đồng loạt khi các bản sao cùng khởi động.
- Khi cơ sở dữ liệu vừa phục hồi, các tác vụ khởi tạo lại có thể cạnh tranh tài nguyên với yêu cầu người dùng.
- Làm nhiễu chẩn đoán: người vận hành thấy nhiều lần restart thay vì một lỗi phụ thuộc chung.

Đây là một ví dụ suy luận từ kiến trúc giả định, không phải mọi sự cố cơ sở dữ liệu đều tạo ra toàn bộ các hậu quả trên. Câu hỏi cần kiểm chứng là: **khởi động lại bản sao có cơ sở để khôi phục trạng thái nội bộ không, hay chỉ lặp lại thất bại của cùng một lời gọi ra ngoài?**

Nếu ứng dụng thực sự bị hỏng trạng thái nội bộ và không thể tự phục hồi, đó là một vấn đề liveness riêng. Không nên kết luận điều này chỉ từ một lần timeout tới cơ sở dữ liệu.

## 3. Readiness có thể kiểm tra phụ thuộc ngoài, nhưng phải có lý do

Readiness thay đổi nơi nhận lưu lượng nên tiêu chí quan trọng là: **đưa bản sao này ra khỏi nhóm nhận yêu cầu có cải thiện kết quả phục vụ không?**

### 3.1. Lỗi chỉ ảnh hưởng một bản sao

Giả sử `orders-a` mất đường kết nối tới cơ sở dữ liệu, còn `orders-b` và `orders-c` vẫn truy cập được. Mọi thao tác đặt hàng đều bắt buộc dùng cơ sở dữ liệu, không có phương án thay thế hợp lệ.

Trong tình huống này, readiness của `orders-a` thất bại là lựa chọn hợp lý:

1. `orders-a` tạm ngừng nhận yêu cầu mới qua Service.
2. Hai bản sao còn lại tiếp tục phục vụ.
3. `orders-a` giữ tiến trình chạy để kết nối có thể tự phục hồi.
4. Khi điều kiện phục vụ khôi phục và probe đạt ngưỡng thành công, bản sao được nhận lưu lượng trở lại.

Lỗi này không nhất thiết đòi hỏi liveness thất bại. Ứng dụng còn hoạt động và cơ chế kết nối lại có thể tự xử lý.

Tuy nhiên, trước khi áp dụng cần kiểm tra hai bản sao còn lại có đủ năng lực nhận thêm tải hay không. Loại một bản sao khỏi phục vụ có thể làm tải tăng lên các bản sao khác; readiness không tạo thêm tài nguyên tính toán.

### 3.2. Lỗi xảy ra ở phụ thuộc dùng chung của mọi bản sao

Bây giờ `orders-db` ngừng hoạt động với toàn bộ nhóm ứng dụng. Nếu đưa `db` vào readiness, cả ba bản sao có thể đồng thời không sẵn sàng.

Điều này có thể phù hợp khi hợp đồng của dịch vụ là “không nhận yêu cầu nếu hoàn toàn không thể thực hiện nghiệp vụ”. Nhưng cần chủ động chấp nhận hậu quả: **không còn bản sao sẵn sàng để nhận yêu cầu qua Service**.

Ngược lại, nếu ứng dụng còn có thể trả lời từ dữ liệu đã lưu, nhận một yêu cầu vào hàng đợi bền vững hoặc trả lỗi nghiệp vụ có kiểm soát, việc loại toàn bộ bản sao có thể làm mất luôn những khả năng đó.

Không có quy tắc “phụ thuộc dùng chung thì luôn đưa vào” hoặc “luôn bỏ ra”. Hai lựa chọn cần được so sánh trên cùng một hợp đồng:

| Lựa chọn khi phụ thuộc chung bị lỗi | Điều cần chấp nhận và kiểm chứng |
| --- | --- |
| Đưa phụ thuộc vào readiness | Toàn nhóm có thể ngừng nhận lưu lượng; tầng phía trước phải có hành vi phù hợp khi không còn đích sẵn sàng |
| Không đưa phụ thuộc vào readiness | Ứng dụng tiếp tục nhận yêu cầu; từng thao tác phải có timeout, phản hồi lỗi hoặc phương án thay thế rõ ràng |

Không hứa rằng người dùng luôn nhận HTTP `503` khi mọi Pod đều không sẵn sàng. Kết quả bên ngoài còn phụ thuộc Service, Ingress và bộ cân bằng tải; mã HTTP của endpoint probe là một câu chuyện khác.

### 3.3. Phụ thuộc không bắt buộc hoặc đã có phương án thay thế

Ví dụ dịch vụ bán hàng dùng hệ thống gợi ý sản phẩm. Khi hệ thống gợi ý lỗi, ứng dụng vẫn hiển thị được sản phẩm, giá và chức năng đặt hàng; phần gợi ý được ẩn đi theo thiết kế.

Nếu hợp đồng phục vụ cho phép chế độ này, không nên biến lỗi gợi ý thành điều kiện readiness thất bại của toàn bộ ứng dụng.

Một số tình huống cần phân tích tương tự:

- Redis chỉ tăng tốc truy vấn, ứng dụng vẫn truy cập được cơ sở dữ liệu với tải chấp nhận được.
- Dịch vụ gửi email tạm lỗi, còn yêu cầu đã được ghi vào cơ chế xử lý lại bền vững.
- API của đối tác chỉ dùng cho một chức năng phụ, các chức năng còn lại vẫn hữu ích.

**Có cơ chế ngắt mạch (circuit breaker) không tự động có nghĩa là còn phục vụ được.** Ngắt mạch chỉ ngăn tiếp tục gọi một đích đang lỗi. Cần một phương án dự phòng (fallback) đáp ứng nghiệp vụ; trả dữ liệu sai hoặc báo thành công cho việc chưa hoàn tất không phải dự phòng hợp lệ.

Các lựa chọn readiness ở phần này phù hợp với định hướng của [Spring Boot về kiểm tra trạng thái ngoài](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state). Việc chọn hợp đồng cụ thể vẫn là trách nhiệm thiết kế của ứng dụng.

## 4. Bộ câu hỏi để quyết định từng phụ thuộc

Hãy xét từng phụ thuộc thay vì đưa toàn bộ kết quả health tổng vào cả hai probe.

1. **Nghiệp vụ nào cần phụ thuộc này?** Nếu chỉ một tính năng phụ cần nó, loại cả bản sao có thể quá rộng.
2. **Khi nó lỗi, bản sao còn đáp ứng được hợp đồng tối thiểu không?** Ghi rõ có thể làm gì và không thể làm gì.
3. **Lỗi riêng từng bản sao hay đồng thời toàn nhóm?** Chuyển lưu lượng chỉ có ích nếu đích khác thực sự tốt hơn.
4. **Khởi động lại sửa được gì?** Lỗi hệ thống ngoài thường không được sửa bằng restart tiến trình gọi.
5. **Từ chối lưu lượng có gây mất khả năng phục vụ còn lại không?** Đặc biệt khi mọi bản sao cùng bị loại.
6. **Tín hiệu kiểm tra gần với nghiệp vụ đến đâu?** Mở được socket chưa chứng minh truy vấn hoặc giao dịch thực tế thành công.
7. **Chi phí và độ trễ kiểm tra là bao nhiêu?** Bản thân probe không được trở thành nguồn gây quá tải.
8. **Điều kiện trở lại phục vụ là gì?** Cần thử cả chiều phục hồi, không chỉ chiều phát hiện lỗi.

Ví dụ bảng quyết định của một ứng dụng giả định:

| Sự cố | Liveness | Readiness | Cơ sở lựa chọn |
| --- | --- | --- | --- |
| API gợi ý lỗi, phần bán hàng vẫn đáp ứng hợp đồng | Giữ thành công nếu tiến trình khỏe | Giữ thành công | Phương án dự phòng còn hữu ích |
| Một bản sao mất kết nối DB bắt buộc, bản sao khác vẫn tốt | Giữ thành công nếu có thể tự phục hồi | Thất bại ở bản sao bị ảnh hưởng | Chuyển yêu cầu sang nơi có thể xử lý |
| DB chung lỗi, mọi thao tác đều bắt buộc DB | Không thất bại chỉ vì DB | Quyết định theo hợp đồng đã chọn | Cân nhắc ngừng nhận toàn nhóm và xử lý lỗi ở tầng ứng dụng |
| Trạng thái nội bộ hỏng vĩnh viễn, restart có thể tạo lại | Có thể thất bại | Không nên tiếp tục nhận yêu cầu | Hành động restart tác động tới nguyên nhân nội bộ |

Các ô trong bảng là quyết định thiết kế theo giả định đã nêu, không phải phản ứng tự động của Spring Boot trước mọi lỗi thực tế.

## 5. Ánh xạ quyết định sang Spring Boot Actuator

Các đoạn cấu hình sau dành cho một ứng dụng web Spring Boot 3.3.x đã có `spring-boot-starter-actuator`. Đây là các đoạn ghép vào cấu hình ứng dụng, không phải một dự án độc lập.

### 5.1. Bắt đầu bằng hai nhóm tách biệt

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

Hai địa chỉ mặc định:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

`probes.enabled: true` giúp bật nhóm probe cả khi thử ngoài Kubernetes. Hai danh sách `include` nêu rõ thành viên mong muốn của từng nhóm. Cấu hình này chưa chọn bất kỳ phụ thuộc ngoài nào làm điều kiện readiness.

Cấu hình mặc định của Spring Boot cũng không tự đưa mọi health indicator của phụ thuộc vào hai nhóm probe. Xem [Kubernetes Probes trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

### 5.2. Chỉ thêm DB vào readiness sau khi đã quyết định nghiệp vụ

Nếu ứng dụng có health contributor `db` và chính sách yêu cầu loại bản sao không truy cập được DB khỏi phục vụ, thay danh sách readiness bằng:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

Đoạn này **thay phần cấu hình tương ứng** trong ví dụ trước; không tạo thêm hai khóa `management` trùng nhau trong cùng tài liệu YAML.

Chỉ áp dụng khi `db` thực sự tồn tại, chẳng hạn ứng dụng đã cấu hình `DataSource` và indicator tương ứng được bật. Đừng sao chép tên contributor không có trong ứng dụng hoặc tắt kiểm tra thành viên nhóm để che lỗi cấu hình.

Giữ `readinessState` để điều kiện vòng đời của ứng dụng tiếp tục tham gia quyết định. Không thay toàn bộ readiness bằng một phép ping DB.

Với các thành viên này và ánh xạ HTTP mặc định, khi DB báo `DOWN` còn ứng dụng vẫn sống:

~~~text
GET /actuator/health/liveness   -> 200
GET /actuator/health/readiness  -> 503
~~~

Đây là kết quả có điều kiện của cấu hình đã mô tả; nếu thay bộ tổng hợp trạng thái hoặc ánh xạ mã HTTP thì phải xác minh lại. HTTP `503` ở đây là phản hồi từ endpoint readiness, không phải cam kết về mã lỗi người dùng sẽ nhận ở Ingress.

**Không nên trỏ liveness vào `/actuator/health` tổng.** Nếu health tổng chứa DB hoặc Redis, chúng có thể vô tình trở thành điều kiện restart mặc dù mục đích ban đầu chỉ là giám sát.

### 5.3. Phân biệt trạng thái nội bộ với kết quả tổng hợp của nhóm

Một phép kiểm tra DB báo `DOWN` trong nhóm readiness không có nghĩa Spring Boot tự đổi `ReadinessState` thành `REFUSING_TRAFFIC`.

Có hai lớp cần phân biệt:

- Trạng thái vòng đời hoặc trạng thái khả dụng do ứng dụng quản lý.
- Kết quả health được tổng hợp từ các contributor mà nhóm đã chọn.

Vì vậy, khi chẩn đoán cần biết nhóm thất bại do thành viên nào. Không suy luận rằng JVM hoặc toàn bộ `ApplicationContext` đã hỏng chỉ vì một nhóm health trả kết quả không tốt.

## 6. Ví dụ Java 17+ chạy độc lập để kiểm chứng lập luận

Chương trình sau mô hình hóa một **chính sách minh họa**:

- Liveness phụ thuộc tình trạng nội bộ.
- Readiness đòi hỏi ứng dụng đã hoàn tất khởi tạo.
- Khi một phụ thuộc bắt buộc không hoạt động và không có dự phòng hợp lệ, readiness thất bại.
- Phụ thuộc không bắt buộc không làm cả ứng dụng ngừng sẵn sàng.

Đây là mô hình logic tự viết; nó không chạy Actuator, không thực hiện kết nối mạng và không mô phỏng ngưỡng của kubelet.

Lưu thành `ProbePolicyDemo.java`:

~~~java
public class ProbePolicyDemo {
    record Situation(
            boolean internalHealthy,
            boolean startupComplete,
            boolean dependencyRequired,
            boolean dependencyReachable,
            boolean fallbackUsable) {
    }

    static boolean live(Situation situation) {
        return situation.internalHealthy();
    }

    static boolean ready(Situation situation) {
        boolean canServe = !situation.dependencyRequired()
                || situation.dependencyReachable()
                || situation.fallbackUsable();

        return live(situation)
                && situation.startupComplete()
                && canServe;
    }

    static void show(String name, Situation situation) {
        System.out.printf(
                "%s: live=%s, ready=%s%n",
                name, live(situation), ready(situation));
    }

    public static void main(String[] args) {
        show("required-db-down",
                new Situation(true, true, true, false, false));
        show("optional-api-down",
                new Situation(true, true, false, false, false));
        show("valid-fallback",
                new Situation(true, true, true, false, true));
        show("internal-broken",
                new Situation(false, true, true, true, false));
        show("starting",
                new Situation(true, false, true, true, false));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 ProbePolicyDemo.java
java ProbePolicyDemo
~~~

Stdout:

~~~text
required-db-down: live=true, ready=false
optional-api-down: live=true, ready=true
valid-fallback: live=true, ready=true
internal-broken: live=false, ready=false
starting: live=true, ready=false
~~~

Dòng đầu thể hiện điểm chính: không dùng được phụ thuộc bắt buộc có thể khiến bản sao không sẵn sàng mà không kết luận tiến trình cần restart.

Chương trình chủ động yêu cầu `internalHealthy` trong readiness. Đây là lựa chọn của mô hình này; không suy ra Spring Boot mặc định tự đưa `livenessState` vào nhóm readiness. Tương tự, chương trình chưa thể hiện “lỗi chỉ một Pod hay toàn nhóm”; đó là dữ kiện kiến trúc phải xét trước khi chọn chính sách.

## 7. Probe cũng tạo tải và có thể khuếch đại sự cố

Giả sử có 60 Pod, mỗi Pod kiểm tra một phụ thuộc sau mỗi 5 giây, mỗi lần thực hiện một lời gọi. Khi chạy ổn định và bỏ qua các cơ chế điều chỉnh lịch kiểm tra, tải danh nghĩa do probe tạo ra là:

~~~text
60 Pod / 5 giây = 12 lời gọi mỗi giây
~~~

Nếu cùng có ba nhóm kiểm tra trùng lặp và mỗi lời gọi lại thử ba lần, số lượt gọi có thể lớn hơn đáng kể. Đây là phép tính dung lượng minh họa, không phải cam kết về lịch gọi thực tế của kubelet.

Khi thiết kế kiểm tra phụ thuộc ngoài:

- Đặt thời hạn hữu hạn cho lấy kết nối, kết nối mạng và đọc phản hồi; ngân sách toàn phép kiểm tra phải phù hợp thời hạn probe.
- Tránh thử lại kéo dài trong luồng xử lý probe; việc thử lại có thể khiến một lỗi ngắn trở thành hàng loạt kiểm tra bị treo.
- Không thực hiện truy vấn nặng hoặc thao tác ghi nghiệp vụ chỉ để chứng minh “còn sống”.
- Nếu dùng kết quả kiểm tra được lưu tạm, ghi rõ tuổi dữ liệu chấp nhận được và cách xử lý khi quá cũ; kết quả `UP` từ lâu không chứng minh phụ thuộc đang tốt.
- Khi có nhiều kiểm tra, cân nhắc tổng độ trễ của cả nhóm, không chỉ timeout của từng lời gọi.
- Thử khả năng phục hồi với số bản sao thực tế, tránh mọi bản sao đồng thời dồn kết nối vào phụ thuộc vừa hoạt động lại.

Loại DB khỏi liveness **không đủ** nếu yêu cầu nghiệp vụ đang giữ hết luồng máy chủ vì chờ DB vô hạn. Khi đó HTTP liveness có thể không được phục vụ kịp và vẫn thất bại. Cần giới hạn thời gian chờ và tách tài nguyên xử lý để một phụ thuộc chậm không chiếm hết khả năng phản hồi của ứng dụng.

## 8. Cấu hình và kiểm chứng hành động của Kubernetes

Đây là đoạn cấu hình đặt dưới một phần tử `containers` của Pod hoặc Deployment. Giả định endpoint Actuator phục vụ trên cổng `8080`:

~~~yaml
ports:
  - name: http
    containerPort: 8080

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 2
~~~

Các con số là ví dụ để thảo luận, cần điều chỉnh theo thời gian đáp ứng và mục tiêu phục hồi thực tế. `successThreshold: 2` của readiness yêu cầu hai lần thành công liên tiếp để phục hồi sau thất bại; không đặt ngưỡng thành công lớn hơn một cho liveness.

Nếu ứng dụng khởi động chậm, cân nhắc `startupProbe` để có ngân sách khởi động phù hợp. Việc chưa sẵn sàng không tự ngăn liveness khởi động lại container. Xem [cấu hình ngưỡng và startup probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Nếu Actuator dùng cổng quản trị riêng, một probe xanh trên cổng đó chưa chứng minh cổng nghiệp vụ vẫn tiếp nhận kết nối. Cần kiểm chứng đúng đường phục vụ; không chỉ kiểm tra máy chủ quản trị.

### Kịch bản thực hành có tiêu chí quan sát

Thực hiện trong môi trường thử nghiệm với ít nhất hai bản sao và giữ cấu hình liveness/readiness tách biệt:

| Bước gây lỗi | Quan sát cần có với chính sách đã chọn |
| --- | --- |
| Chặn DB chỉ từ một Pod, DB bắt buộc có trong readiness | Readiness của Pod đó thất bại; Pod khác còn phục vụ; liveness không thất bại chỉ vì indicator DB |
| Khôi phục kết nối của Pod bị ảnh hưởng | Pod trở lại Ready sau các ngưỡng đã cấu hình, không cần triển khai lại |
| Chặn DB dùng chung | Xác minh có chủ động chấp nhận cả nhóm không Ready hay vẫn giữ lưu lượng để ứng dụng xử lý lỗi |
| Làm API tùy chọn thất bại | Chức năng dự phòng thực sự hoạt động, không chỉ probe vẫn xanh |
| Làm phụ thuộc phản hồi rất chậm | Thời gian probe được chặn trên; không xuất hiện vòng tích tụ yêu cầu kiểm tra |

Với giả định cổng mặc định, có thể xem mã HTTP trên máy chạy ứng dụng bằng:

~~~shell
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/health/liveness
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/health/readiness
~~~

Hai lệnh trên dùng cú pháp shell kiểu Unix. Trên Windows, gọi `curl.exe` và dùng đường dẫn đích bỏ dữ liệu phù hợp. Điều kiện truy cập endpoint và quy tắc xác thực phải cho phép probe nhận đúng kết quả; lỗi `401` hoặc `403` không chứng minh phụ thuộc bị hỏng.

So sánh đồng thời mã HTTP probe, trạng thái Ready, số lần restart, lỗi nghiệp vụ và độ trễ. Probe xanh chỉ xác nhận điều kiện đã thiết kế; nó không thay thế phép kiểm thử một yêu cầu nghiệp vụ thực tế.

## 9. Các lỗi thiết kế dễ gặp

| Cách làm | Vấn đề | Cách suy nghĩ lại |
| --- | --- | --- |
| Dùng health tổng cho mọi probe | Lỗi phụ thuộc có thể biến thành restart hàng loạt | Thiết kế thành viên từng nhóm theo hành động cần kích hoạt |
| Thêm mọi DB, cache, API vào readiness | Một chức năng phụ có thể làm mất toàn bộ khả năng phục vụ | Xác định hợp đồng tối thiểu và dự phòng hợp lệ |
| Cho rằng readiness thất bại sẽ tự sửa ứng dụng | Readiness chỉ thay đổi khả năng nhận lưu lượng | Thiết kế riêng cơ chế kết nối lại và phục hồi |
| Giữ readiness xanh nhưng không xử lý lỗi nghiệp vụ | Yêu cầu tiếp tục vào rồi treo hoặc thất bại không kiểm soát | Có thời hạn chờ, phản hồi lỗi và giới hạn tài nguyên |
| Kiểm tra kết nối quá sơ sài | Kết nối được chưa chắc thực hiện được thao tác cần thiết | Chọn phép kiểm tra đủ đại diện với chi phí phù hợp |
| Tăng timeout rất lớn để bớt báo lỗi | Chậm phát hiện và có thể giữ tài nguyên lâu hơn | Đặt ngân sách dựa trên mục tiêu phục vụ, thử lỗi chậm thực tế |
| Chỉ thử lúc phụ thuộc bị hỏng | Bản sao có thể không trở lại phục vụ đúng cách | Kiểm chứng cả mất kết nối và phục hồi |

## 10. Tự kiểm tra cách hiểu

**Tình huống 1:** Redis chỉ dùng làm bộ nhớ đệm. Khi Redis lỗi, ứng dụng đọc DB trực tiếp nhưng DB không đủ sức gánh toàn bộ tải. Có thể giữ readiness xanh chỉ vì “đã có fallback” không?

Không thể kết luận như vậy. Phải thử năng lực phục vụ của đường dự phòng và có cơ chế giới hạn tải phù hợp. Một phương án dự phòng có tồn tại trong mã nhưng sụp đổ dưới tải thực tế chưa bảo đảm hợp đồng phục vụ.

**Tình huống 2:** Cả năm Pod cùng không truy cập được dịch vụ thanh toán. Restart năm Pod có giúp dịch vụ thanh toán hoạt động lại không?

Với giả định lỗi ở dịch vụ thanh toán, không. Cần quyết định chức năng nào vẫn phục vụ được và việc loại toàn nhóm khỏi lưu lượng có phù hợp không; không đưa lỗi thanh toán trực tiếp vào liveness.

**Tình huống 3:** Readiness trả `503` vì DB `DOWN`, còn liveness trả `200`. Hai tín hiệu có mâu thuẫn không?

Không. Một bản sao có thể đang hoạt động và có khả năng tự phục hồi nhưng tạm thời không đáp ứng điều kiện nhận yêu cầu mới. Chính việc tách hai quyết định giúp tránh dùng restart để xử lý một sự cố mà restart không giải quyết được.
