# Phân biệt sức khỏe kỹ thuật, khả năng phục vụ và tính đúng đắn nghiệp vụ

Một dịch vụ bán hàng trả `{"status":"UP"}` từ Actuator. Bộ cân bằng tải vẫn gửi yêu cầu đến dịch vụ. Tuy nhiên, đơn hàng được giảm 10% lại bị tính sai số tiền phải trả. Ba quan sát này có thể đồng thời đúng vì chúng trả lời **ba câu hỏi khác nhau**.

Bài này xây dựng cách đọc tín hiệu health trong Spring Boot 3.3.x: hiểu hệ thống đang kiểm tra điều gì, quyết định vận hành nào có thể dựa vào kết quả đó và bằng chứng nào còn thiếu để kết luận một nghiệp vụ hoạt động đúng.

## 1. Ba khái niệm cần tách rõ

| Khía cạnh | Câu hỏi chính | Ví dụ bằng chứng | Quyết định thường liên quan |
| --- | --- | --- | --- |
| Sức khỏe kỹ thuật | Các điều kiện kỹ thuật được quan sát có đang hoạt động trong giới hạn cho phép không? | Tiến trình phản hồi, kết nối cơ sở dữ liệu thành công, dung lượng đĩa còn đủ | Điều tra thành phần lỗi, đánh giá tài nguyên và phụ thuộc |
| Khả năng phục vụ | Bản chạy này có nên nhận và có đủ điều kiện xử lý loại yêu cầu đang xét vào lúc này không? | Đã khởi tạo xong, dữ liệu thiết yếu sẵn sàng, chưa chủ động từ chối lưu lượng | Cho nhận yêu cầu mới, tạm rút khỏi luồng phân phối |
| Tính đúng đắn nghiệp vụ | Kết quả và thay đổi trạng thái có tuân thủ quy tắc của miền nghiệp vụ không? | Tính đúng giá, không trừ kho hai lần, không ghi nhận thanh toán trùng | Chấp nhận kết quả, sửa lỗi logic, đối soát hoặc khôi phục dữ liệu |

Trong bài, **sức khỏe kỹ thuật** là một góc nhìn do người thiết kế chọn; đây không phải tên một trạng thái chuẩn riêng của Spring Boot. Nó cũng không đồng nghĩa hoàn toàn với liveness. Một kết nối cơ sở dữ liệu là tín hiệu kỹ thuật hữu ích nhưng không vì thế mà phải đưa vào liveness.

**Khả năng phục vụ** cần gắn với phạm vi cụ thể: phục vụ chức năng nào, cho đối tượng nào và với yêu cầu chất lượng nào? Một ứng dụng có thể đọc danh mục từ bộ nhớ đệm nhưng không thể tạo đơn khi cơ sở dữ liệu mất kết nối.

**Tính đúng đắn nghiệp vụ** cần một chuẩn đối chiếu. Một phản hồi nhanh và không có exception vẫn có thể chứa kết quả sai.

### Mối liên hệ giữa ba khía cạnh

Điều kiện kỹ thuật và điều kiện sẵn sàng hỗ trợ việc thực hiện nghiệp vụ. Chúng không tự chứng minh quy tắc nghiệp vụ đã được triển khai đúng.

```text
Quan sát kỹ thuật     → hỗ trợ chẩn đoán điều kiện vận hành
Chính sách sẵn sàng   → hỗ trợ quyết định nhận yêu cầu mới
Kiểm chứng nghiệp vụ  → đối chiếu kết quả và tác động với quy tắc
```

Ba loại bằng chứng bổ sung cho nhau. Chúng không tạo thành một chuỗi suy luận chắc chắn rằng “kỹ thuật tốt → sẵn sàng → mọi kết quả đều đúng”.

## 2. Vì sao cùng một màu xanh có thể gây hiểu nhầm?

Xét ba phép kiểm tra trong một dịch vụ đặt hàng:

1. Kiểm tra có mở được kết nối cơ sở dữ liệu không.
2. Kiểm tra bản chạy đã sẵn sàng nhận yêu cầu chưa.
3. Kiểm tra đơn giá 10.000 đơn vị tiền nhỏ nhất, giảm 10%, phải còn 9.000.

Phép kiểm tra thứ nhất không chạy phép tính giảm giá. Phép kiểm tra thứ hai có thể chỉ đọc trạng thái vòng đời của ứng dụng. Nếu phép tính thực tế trả 9.990, hai phép kiểm tra đầu vẫn có thể thành công.

Một health check luôn có **ranh giới quan sát**:

- Nó kiểm tra những thành phần và điều kiện nào?
- Có đi qua luồng xử lý thật của người dùng không?
- Có kiểm tra kết quả hay chỉ kiểm tra khả năng kết nối?
- Kết quả được quan sát vào thời điểm nào?
- Thành công hoặc thất bại sẽ dẫn đến hành động gì?

Không có thông tin này, một giá trị UP rất dễ bị diễn giải rộng hơn bằng chứng thực tế.

## 3. Các tình huống cho thấy ba khía cạnh có thể khác nhau

| Tình huống | Quan sát kỹ thuật | Khả năng phục vụ | Tính đúng đắn nghiệp vụ |
| --- | --- | --- | --- |
| Ứng dụng đang nạp dữ liệu khởi tạo | Tiến trình và kết nối đều hoạt động | Có thể chưa nên nhận yêu cầu | Không suy ra từ việc đang khởi tạo |
| Cơ sở dữ liệu bắt buộc bị mất kết nối | Có lỗi ở phụ thuộc kỹ thuật | Luồng cần ghi dữ liệu có thể không phục vụ được | Logic tính toán vẫn có thể đúng trong kiểm thử độc lập |
| Dịch vụ gợi ý sản phẩm lỗi nhưng có phương án bỏ gợi ý | Một phụ thuộc không hoạt động | Luồng đặt hàng vẫn có thể phục vụ theo chính sách đã chọn | Cần kiểm tra kết quả của luồng suy giảm chức năng |
| Công thức giảm giá bị viết sai | Các kiểm tra kết nối có thể đều tốt | Bản chạy vẫn có thể đang nhận yêu cầu | Sai kết quả tính tiền |
| Webhook thanh toán được xử lý hai lần | HTTP và cơ sở dữ liệu có thể bình thường | Endpoint vẫn tiếp nhận được webhook | Có thể vi phạm yêu cầu chỉ ghi nhận một lần |
| Thời gian phản hồi vượt mục tiêu của người dùng | Probe nhẹ vẫn có thể thành công | Chất lượng phục vụ không đạt yêu cầu | Kết quả có thể đúng nhưng đến quá muộn |

Cột nghiệp vụ không nên mặc định ghi “đúng” chỉ vì chưa quan sát thấy sai. **Chưa kiểm chứng** là một kết luận hợp lệ và chính xác hơn.

Một lỗi logic cũng có thể làm yêu cầu ném exception hoặc thất bại. Tách ba khía cạnh không có nghĩa chúng không ảnh hưởng lẫn nhau; mục đích là biết mỗi bằng chứng hỗ trợ kết luận nào.

## 4. Spring Boot biểu diễn các tín hiệu này ra sao?

### 4.1. Endpoint health là kết quả tổng hợp theo cấu hình

Một `HealthIndicator` đóng góp kết quả `Health` cho endpoint health. Người viết indicator quyết định phép kiểm tra thực tế, còn cấu hình xác định nhóm và cách tổng hợp được sử dụng. [Hợp đồng HealthIndicator trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Vì vậy:

```text
/actuator/health = kết quả của các phép kiểm tra được chọn
                  và chính sách tổng hợp đang áp dụng
```

Endpoint gốc có thể chứa kiểm tra kỹ thuật, trạng thái vòng đời và indicator do ứng dụng tự viết. Không nên mặc định coi nó là một chứng nhận đầy đủ về chất lượng sản phẩm.

Ví dụ, kiểm tra “mở được kết nối cơ sở dữ liệu” không chứng minh rằng:

- Câu truy vấn của chức năng đặt hàng đúng.
- Người gọi có đúng quyền truy cập dữ liệu.
- Giao dịch ghi đơn và trừ kho bảo toàn bất biến.
- Schema và dữ liệu đáp ứng mọi nhánh xử lý.
- Đơn hàng đã được thanh toán đúng một lần.

### 4.2. Liveness và readiness phục vụ các quyết định khác nhau

Spring Boot có các trạng thái sẵn có trong `ApplicationAvailability`:

| Loại | Trạng thái ứng dụng | Ý nghĩa cần quan tâm |
| --- | --- | --- |
| Liveness | `LivenessState.CORRECT` / `BROKEN` | Trạng thái nội tại cho phép tiếp tục hoạt động hoặc đã hỏng đến mức cần can thiệp |
| Readiness | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Ứng dụng đang chấp nhận hay từ chối lưu lượng mới |

Boot cung cấp cơ chế đọc và cập nhật các trạng thái này. Chúng phản ánh trạng thái do vòng đời hoặc mã ứng dụng công bố, không tự kiểm tra mọi quy tắc nghiệp vụ. [ApplicationAvailability của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).

Một `ReadinessStateHealthIndicator` là indicator đọc trạng thái readiness của ứng dụng. Nó không tự thực hiện một giao dịch đặt hàng để xác minh kết quả. [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html).

Trong vòng đời thông thường, ứng dụng có thể đã hoạt động ở mức nội tại nhưng vẫn chưa nhận lưu lượng khi đang thực hiện các tác vụ khởi động. Boot coi ứng dụng sẵn sàng sau khi các application runner và command-line runner đã được gọi xong. Một tác vụ nạp dữ liệu tự khởi chạy bất đồng bộ ngoài ranh giới đó cần chính sách sẵn sàng phù hợp; không nên giả định Boot tự biết nó đã hoàn thành. [Application availability và vòng đời SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 4.3. Readiness là tín hiệu cho hệ thống phân phối lưu lượng

Trong Kubernetes, probe readiness thất bại làm bản chạy không còn là đích sẵn sàng cho lưu lượng Service thông thường. Probe liveness thất bại đến ngưỡng cấu hình có thể dẫn đến khởi động lại container theo chính sách khởi động lại. Readiness thất bại không tự mang ý nghĩa “phải khởi động lại”. [Các loại probe và hành động của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Việc ngừng gửi yêu cầu mới cũng không đồng nghĩa mọi yêu cầu đang xử lý đều đã hoàn tất. Quản lý yêu cầu đang chạy và tắt ứng dụng có trật tự cần cơ chế thích hợp.

Ngoài Kubernetes, readiness chỉ có tác động vận hành nếu bộ cân bằng tải hoặc nền tảng triển khai được cấu hình sử dụng tín hiệu đó. Bản thân một URL trả OUT_OF_SERVICE không tự cấu hình toàn bộ hạ tầng.

## 5. Đọc health group mà không suy diễn quá phạm vi

Giả sử có một ứng dụng Spring Boot 3.3.x dùng Java 21, Spring Web và Actuator. Có thể khai báo rõ hai nhóm cơ bản trong `application.yml`:

```yaml
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
          include:
            - livenessState
        readiness:
          include:
            - readinessState
```

Đây là đoạn cấu hình cho ứng dụng Spring Boot đã có, không phải một dự án Java độc lập.

Đọc cấu hình theo đúng phạm vi:

- Nhóm liveness đọc `livenessState`.
- Nhóm readiness đọc `readinessState`.
- Cấu hình này chưa thêm kiểm tra cơ sở dữ liệu vào readiness.
- Nó chưa thêm một phép kiểm chứng giá bán hay quy tắc thanh toán nào.

Trong Boot 3.3, các probe được hỗ trợ qua health group; ngoài môi trường Kubernetes có thể bật chúng bằng `management.endpoint.health.probes.enabled`. Mặc định, Boot không tự thêm các indicator phụ thuộc bên ngoài vào hai nhóm probe. [Health group và Kubernetes probes của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Với địa chỉ mặc định và trong PowerShell trên Windows, có thể gọi:

```powershell
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
```

Trên Linux/macOS, thay `curl.exe` bằng `curl`. Nếu ứng dụng đã khởi động hoàn tất, các trạng thái đang bình thường, giữ ánh xạ HTTP mặc định và yêu cầu được phép truy cập, mỗi endpoint probe trên sẽ trả HTTP 200 với trạng thái UP. Điều đó vẫn không kiểm chứng công thức tính tiền.

Nếu ứng dụng dùng cổng, context path hoặc cơ chế xác thực khác, phải gọi theo cấu hình thực tế. Phản hồi 401/403 cho biết yêu cầu đang gặp quyết định bảo mật; không thể chỉ từ đó kết luận một phụ thuộc nghiệp vụ đang lỗi.

### Cơ sở dữ liệu lỗi nhưng readiness vẫn UP có mâu thuẫn không?

Không nhất thiết. Nếu readiness chỉ gồm `readinessState` và trạng thái ứng dụng vẫn là ACCEPTING_TRAFFIC, một indicator `db` thất bại ở nhóm khác không tự trở thành thành viên readiness.

Khi diễn giải hai kết quả, cần đọc **danh sách thành viên nhóm**, không chỉ so sánh hai URL đều chứa từ health.

## 6. Chọn kiểm tra phụ thuộc theo hành động muốn thực hiện

Một dịch vụ bên ngoài thất bại không luôn đòi hỏi cùng một phản ứng.

### Trường hợp A: phụ thuộc cần thiết cho mọi yêu cầu quan trọng

Nếu bản chạy không thể thực hiện chức năng thiết yếu khi thiếu cơ sở dữ liệu, nhóm phát triển có thể cân nhắc đưa kiểm tra đó vào readiness.

Ví dụ cấu hình thay thế cho phần readiness:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
```

Chỉ dùng tên `db` khi ứng dụng thực sự có contributor tương ứng. Đây là thay đổi chính sách sẵn sàng, không phải một cách tự kiểm chứng mọi thao tác đọc/ghi nghiệp vụ.

### Trường hợp B: phụ thuộc có phương án phục vụ suy giảm

Nếu dịch vụ gợi ý lỗi nhưng vẫn cho phép đặt hàng mà không hiển thị gợi ý, đưa dịch vụ gợi ý vào readiness có thể làm mất luôn chức năng đặt hàng đang sử dụng được.

Cần mô tả rõ chế độ suy giảm: chức năng nào còn được hỗ trợ, kết quả nào phải thay đổi và giới hạn chất lượng nào được chấp nhận.

### Trường hợp C: phụ thuộc được mọi bản chạy dùng chung

Nếu tất cả bản chạy cùng mất kết nối một cơ sở dữ liệu dùng chung, đưa phụ thuộc đó vào readiness có thể làm tất cả cùng bị rút khỏi luồng phục vụ. Điều này có phù hợp hay không phụ thuộc chính sách sản phẩm và cách xử lý lỗi ở tầng trên.

Không đưa kiểm tra phụ thuộc bên ngoài vào liveness chỉ vì đó là tín hiệu kỹ thuật. Nếu lỗi bên ngoài làm mọi container liên tục khởi động lại, việc khởi động lại thường không sửa được nguyên nhân bên ngoài. Thiết kế các quyết định này cần được cân nhắc theo vai trò của từng probe.

## 7. Ví dụ Java chạy độc lập: health tốt nhưng kết quả sai

Chương trình sau mô phỏng ba loại bằng chứng, không kết nối cơ sở dữ liệu thật và không gọi Actuator.

Quy ước riêng của ví dụ:

- `technicalHealthy`: tiến trình phản hồi và cơ sở dữ liệu có thể truy cập.
- `readyForRequests`: hai điều kiện trên đúng và bản chạy cho phép nhận lưu lượng.
- `businessRuleCheck`: phép tính của ca kiểm thử có cho kết quả kỳ vọng 9.000 hay không.

Đây là **chính sách của mô hình minh họa**, không phải thuật toán mặc định của Spring Boot. Chỉ báo kỹ thuật trong ví dụ cũng không phải liveness.

Dùng đơn vị tiền nhỏ nhất dạng số nguyên. Với số tiền gốc 10.000 và giảm 10%, kết quả cần là 9.000. Lỗi cố ý trong `buggyPayableCents` trừ số 10 như một số tiền thay vì tính 10% của giá gốc.

Lưu thành `HealthMeaningDemo.java`:

```java
public class HealthMeaningDemo {
    record RuntimeSnapshot(
            boolean processResponsive,
            boolean databaseReachable,
            boolean acceptingTraffic) {
    }

    static boolean technicalHealthy(RuntimeSnapshot snapshot) {
        return snapshot.processResponsive()
                && snapshot.databaseReachable();
    }

    static boolean readyForRequests(RuntimeSnapshot snapshot) {
        return snapshot.processResponsive()
                && snapshot.databaseReachable()
                && snapshot.acceptingTraffic();
    }

    static long correctPayableCents(long subtotalCents, int discountPercent) {
        return subtotalCents * (100 - discountPercent) / 100;
    }

    static long buggyPayableCents(long subtotalCents, int discountPercent) {
        return subtotalCents - discountPercent;
    }

    static void report(
            String name,
            RuntimeSnapshot snapshot,
            boolean businessRuleCheck) {
        System.out.printf(
                "%s | technical=%s | ready=%s | ruleCheck=%s%n",
                name,
                technicalHealthy(snapshot),
                readyForRequests(snapshot),
                businessRuleCheck);
    }

    public static void main(String[] args) {
        long expectedPayableCents = 9000;
        long correctResult = correctPayableCents(10000, 10);
        long buggyResult = buggyPayableCents(10000, 10);

        report("normal",
                new RuntimeSnapshot(true, true, true),
                correctResult == expectedPayableCents);
        report("warming-up",
                new RuntimeSnapshot(true, true, false),
                correctResult == expectedPayableCents);
        report("database-down",
                new RuntimeSnapshot(true, false, true),
                correctResult == expectedPayableCents);
        report("business-bug",
                new RuntimeSnapshot(true, true, true),
                buggyResult == expectedPayableCents);

        System.out.println("actualPayableCents=" + buggyResult);
        System.out.println("expectedPayableCents=" + expectedPayableCents);
    }
}
```

Biên dịch và chạy bằng JDK 21:

```shell
javac -encoding UTF-8 HealthMeaningDemo.java
java HealthMeaningDemo
```

Stdout:

```text
normal | technical=true | ready=true | ruleCheck=true
warming-up | technical=true | ready=false | ruleCheck=true
database-down | technical=false | ready=false | ruleCheck=true
business-bug | technical=true | ready=true | ruleCheck=false
actualPayableCents=9990
expectedPayableCents=9000
```

### Cách giải thích từng dòng

**normal:** các điều kiện kỹ thuật và nhận lưu lượng đều đạt; ca kiểm thử dùng công thức đúng cũng đạt.

**warming-up:** điều kiện kỹ thuật vẫn đạt nhưng bản chạy chưa chấp nhận lưu lượng. Đây là ví dụ “hoạt động” và “nên nhận thêm yêu cầu” không đồng nhất.

**database-down:** cơ sở dữ liệu không truy cập được nên chính sách readiness của mô hình trả false, dù cờ chấp nhận lưu lượng vẫn là true. Ca kiểm thử công thức đúng vẫn đạt vì nó không phụ thuộc cơ sở dữ liệu.

**business-bug:** mọi điều kiện kỹ thuật và readiness trong mô hình đều đạt nhưng phép tính sai trả 9.990 thay vì 9.000.

Đặc biệt, `ruleCheck=true` ở dòng database-down chỉ nói **ca kiểm thử công thức đang xét đã đạt**. Nó không nói một giao dịch đặt hàng xuyên suốt hệ thống hiện có thể thành công khi cơ sở dữ liệu đang lỗi.

Ví dụ sử dụng số nhỏ và một trường hợp giảm giá đơn giản. Quy tắc làm tròn, giới hạn đầu vào, thuế, nhiều loại tiền và nguy cơ tràn số cần được thiết kế khi triển khai tính tiền thực tế.

## 8. HTTP 200 chưa đủ để kết luận nghiệp vụ đúng

Xét một phản hồi giả định từ chức năng báo giá:

```json
{
  "subtotalCents": 10000,
  "discountPercent": 10,
  "payableCents": 9990
}
```

Nếu phản hồi đi cùng HTTP 200, quan sát ở mức giao thức cho biết yêu cầu đã được phục vụ theo cách endpoint biểu diễn thành công. Muốn phát hiện sai nghiệp vụ, phải đối chiếu `payableCents` với kết quả đúng 9.000.

Có ba mức kiểm chứng khác nhau:

| Phép kiểm chứng | Có thể phát hiện | Chưa đủ để chứng minh |
| --- | --- | --- |
| Chỉ kiểm tra HTTP 200 | Một số lỗi truy cập, giao thức hoặc xử lý được biểu diễn bằng mã lỗi | Nội dung tính tiền đúng |
| Kiểm tra JSON của báo giá | Sai trường hoặc sai số tiền cho ca kiểm thử | Đơn đã lưu và thanh toán đúng |
| Kiểm tra kết quả cùng tác động lưu trữ/thanh toán | Một phần lỗi xuyên suốt, lặp giao dịch hoặc sai dữ liệu | Mọi trường hợp đầu vào và mọi lỗi đồng thời |

Giám sát cần có tín hiệu phù hợp với trải nghiệm thực tế. Google SRE cũng phân biệt lỗi được biểu hiện bằng mã HTTP với trường hợp HTTP thành công nhưng nội dung sai; các trường hợp này cần kiểm tra kết quả chứ không chỉ đếm mã phản hồi. [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals).

Với luồng bất đồng bộ, HTTP 202 hoặc việc đưa thông điệp vào hàng đợi chỉ có thể chứng minh bước tiếp nhận theo hợp đồng của hệ thống. Cần theo dõi kết quả cuối, thời hạn xử lý, sự kiện thất bại và đối soát để biết nghiệp vụ đã hoàn tất đúng.

## 9. Dùng loại bằng chứng nào cho từng câu hỏi?

| Câu hỏi cần trả lời | Bằng chứng thích hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Bản chạy có bị kẹt đến mức cần khởi động lại không? | Liveness được thiết kế theo trạng thái nội tại | Một phép kiểm tra quá nhẹ có thể không phát hiện mọi kiểu kẹt |
| Có nên gửi thêm yêu cầu mới đến bản chạy không? | Readiness và chính sách phân phối lưu lượng | Cần xác định loại yêu cầu và điều kiện thiết yếu |
| Người dùng có nhận phản hồi đủ nhanh không? | Đo độ trễ thực tế, phân vị, tỷ lệ lỗi và mức bão hòa | Probe nhẹ không mô phỏng toàn bộ tải |
| Quy tắc giảm giá có đúng không? | Kiểm thử với đầu vào và kết quả kỳ vọng độc lập | Đừng viết lại cùng công thức sai trong phần tính kỳ vọng |
| Đơn hàng và tồn kho có cập nhật nhất quán không? | Kiểm thử tích hợp, giao dịch và các tình huống đồng thời | Kết nối cơ sở dữ liệu thành công không kiểm chứng bất biến |
| Webhook gửi lại có gây thanh toán trùng không? | Kiểm thử tính lũy đẳng (idempotency), ràng buộc và đối soát | HTTP 200 của mỗi lần gửi không chứng minh chỉ xử lý một lần |
| Một luồng người dùng có hoạt động ngoài môi trường kiểm thử không? | Kiểm tra tổng hợp từ bên ngoài với dữ liệu an toàn | Có phạm vi mẫu, chi phí và rủi ro tác động riêng |
| Dữ liệu thực tế có vi phạm quy tắc sau một thời gian không? | Kiểm tra bất biến, đối soát và theo dõi kết quả nghiệp vụ | Cần xác định độ trễ phát hiện và cách xử lý sai lệch |

Khả năng phục vụ còn có chiều thời gian và chất lượng. Readiness là một tín hiệu theo thời điểm và theo bản chạy; chỉ số mức dịch vụ (SLI) thường quan sát hành vi trong một khoảng thời gian. Chỉ số thành công cần được định nghĩa theo điều người dùng thực sự cần, thay vì chỉ tái sử dụng một nhãn UP. [Service Level Objectives của Google SRE](https://sre.google/sre-book/service-level-objectives/).

Không kiểm thử hay giám sát hữu hạn nào chứng minh mọi trường hợp đều đúng. Cần nêu phạm vi đã kiểm chứng, những trường hợp chưa bao phủ và điều kiện môi trường áp dụng.

## 10. Thiết kế health check để kết quả có ý nghĩa vận hành

Khi thêm một phép kiểm tra, trước hết viết một mô tả ngắn về hợp đồng của nó:

```text
Kiểm tra: kết nối đến cơ sở dữ liệu phục vụ ghi đơn
Phạm vi: một bản chạy, đường kết nối đang sử dụng
Kết luận cho phép: phụ thuộc này truy cập được tại thời điểm kiểm tra
Kết luận chưa có: giao dịch đặt hàng đúng ở mọi trường hợp
Hành động khi lỗi: tùy chính sách readiness hoặc cảnh báo đã được chọn
```

Tiếp theo xem xét các giới hạn thực tế:

1. **Chi phí và thời gian:** đặt giới hạn phù hợp; không biến mỗi probe thành một loạt thao tác tốn kém.
2. **Tác dụng phụ:** tránh tạo đơn, trừ tiền hoặc gửi thông báo thật chỉ để đáp ứng probe tần suất cao.
3. **Phạm vi tài nguyên:** probe có đi qua cùng cổng, đường kết nối và điều kiện gần với luồng cần quan sát không?
4. **Độ mới:** một kết quả được lưu tạm hoặc quan sát trước đó có thể không phản ánh lỗi vừa xảy ra.
5. **Hành động:** lỗi này nên rút lưu lượng, cảnh báo, phục vụ suy giảm hay khởi động lại? Không gán một hành động cho mọi lỗi.

Ví dụ, quản trị và ứng dụng chạy ở hai cổng khác nhau có thể tạo ra hai điều kiện xử lý khác nhau. Một endpoint quản trị phản hồi chưa chứng minh cổng phục vụ người dùng đang nhận yêu cầu tốt. Khi đánh giá bằng chứng, luôn hỏi đường kiểm tra đã thực sự đi qua phần nào của hệ thống.

Một phép kiểm tra tổng hợp nghiệp vụ có giá trị, nhưng thường nên có tần suất, dữ liệu, môi trường và chính sách xử lý riêng. Việc gắn trực tiếp nó vào liveness cần được đánh giá rất kỹ vì thất bại của giao dịch mẫu có thể kích hoạt khởi động lại ngoài ý muốn.

## 11. Các lỗi suy luận thường gặp

| Suy luận | Vì sao chưa đủ? | Cách kiểm tra tiếp |
| --- | --- | --- |
| “Health UP nên nghiệp vụ chắc chắn đúng” | Chưa biết indicator có kiểm tra nghiệp vụ đó không | Đọc hợp đồng kiểm tra và kiểm chứng kết quả thực tế |
| “Readiness UP nên mọi khách đều dùng được” | Danh tính, quyền, tuyến mạng và dữ liệu của từng khách có thể khác | Kiểm tra từ đường truy cập và danh tính đại diện |
| “Có lỗi phụ thuộc thì phải cho liveness DOWN” | Khởi động lại không nhất thiết sửa được lỗi bên ngoài | Chọn hành động theo khả năng tự phục hồi và vai trò phụ thuộc |
| “Readiness lỗi thì container sẽ tự khởi động lại” | Readiness chủ yếu phục vụ quyết định gửi lưu lượng | Xem cấu hình liveness, restart và nền tảng thực tế |
| “Cơ sở dữ liệu kết nối được nên giao dịch đúng” | Kết nối không kiểm tra logic, ràng buộc và tính đồng thời | Kiểm thử giao dịch, bất biến và trường hợp cạnh tranh |
| “Tất cả kiểm thử đơn vị đạt nên hệ thống đang phục vụ được” | Kiểm thử độc lập có thể không sử dụng môi trường triển khai | Bổ sung kiểm thử tích hợp và quan sát vận hành |
| “Một yêu cầu mẫu thành công chứng minh toàn bộ hệ thống tốt” | Mẫu chỉ bao phủ một nhánh và một thời điểm | Xác định phạm vi mẫu và kết hợp nhiều loại bằng chứng |

Khi xử lý sự cố, dùng phát biểu có giới hạn cụ thể: “readinessState đang ACCEPTING_TRAFFIC”, “phép kiểm tra kết nối đã thành công” hoặc “ca giảm giá 10% với giá gốc 10.000 đã đạt”. Những phát biểu này giúp tránh chuyển một kết quả hẹp thành cam kết quá rộng.

## 12. Thực hành: chọn bằng chứng và hành động phù hợp

Với mỗi tình huống, ghi ba ý: đã biết điều gì, chưa biết điều gì và cần làm gì tiếp theo.

### Tình huống 1: nhận đơn khi nạp dữ liệu chưa xong

Tiến trình phản hồi, cơ sở dữ liệu truy cập được, nhưng bảng quy tắc giá chưa nạp xong.

- Bằng chứng kỹ thuật hiện có chưa chứng minh bản chạy đã đủ điều kiện báo giá.
- Cần xác định dữ liệu này có phải điều kiện bắt buộc trước khi nhận yêu cầu không.
- Nếu bắt buộc, chính sách readiness phải phản ánh thời gian chưa sẵn sàng; đồng thời kiểm thử kết quả sau khi nạp.

### Tình huống 2: tính giá sai dù các probe đều thành công

Giá gốc 10.000, giảm 10%, API trả 9.990.

- Đã có bằng chứng sai nghiệp vụ cho ca cụ thể.
- Không có cơ sở cho rằng khởi động lại sẽ sửa công thức.
- Cần sửa logic, bổ sung ca kiểm thử theo kết quả kỳ vọng và xem xét dữ liệu đã bị ảnh hưởng.

### Tình huống 3: mất dịch vụ gợi ý, đặt hàng vẫn làm được

- Đã quan sát lỗi một phụ thuộc.
- Cần kiểm tra chức năng suy giảm có đúng hợp đồng và trải nghiệm chấp nhận được không.
- Không tự động rút toàn bộ bản chạy nếu chính sách cho phép tiếp tục đặt hàng.

### Tình huống 4: tiền bị ghi nhận hai lần sau khi webhook gửi lại

- HTTP thành công không chứng minh xử lý lũy đẳng.
- Cần kiểm tra khóa nhận dạng giao dịch, ràng buộc lưu trữ, xử lý đồng thời và đối soát kết quả.
- Probe kỹ thuật hiện có chỉ là một phần thông tin phục vụ điều tra.

### Tự kiểm tra

1. Vì sao một chương trình có `technical=true` và `ready=true` vẫn có thể có `ruleCheck=false`?
2. Vì sao `ruleCheck=true` không đủ kết luận giao dịch đặt hàng thực tế đang thành công?
3. Khi cơ sở dữ liệu lỗi, thông tin nào quyết định đưa lỗi vào readiness hay chỉ cảnh báo?
4. Nếu một probe được gọi mỗi vài giây, vì sao không nên mặc định cho nó thực hiện một thanh toán thật?
5. Trước khi viết “hệ thống hoạt động đúng”, cần nêu rõ phạm vi chức năng, đầu vào, kết quả và thời điểm nào?

Một thiết kế tốt gắn từng tín hiệu với một câu hỏi rõ ràng và một hành động phù hợp. Sức khỏe kỹ thuật giúp quan sát điều kiện vận hành, readiness hỗ trợ quản lý lưu lượng, còn tính đúng đắn nghiệp vụ cần được đối chiếu bằng kết quả và các bất biến của chính nghiệp vụ.
