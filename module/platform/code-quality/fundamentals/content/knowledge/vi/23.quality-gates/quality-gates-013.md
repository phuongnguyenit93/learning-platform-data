# Điều chỉnh quy trình khi chi phí kiểm tra vượt giá trị phản hồi

Một nhóm có pipeline chạy gần một giờ cho mỗi pull request. Hầu hết lần chạy đều thất bại vì lỗi format, import hoặc một unit test rất nhỏ — những lỗi lập trình viên có thể phát hiện trong vài giây ở máy cá nhân. Trong khi đó, các kiểm tra tích hợp quan trọng lại thường bị đẩy xuống cuối pipeline, nơi phải chờ lâu mới có kết quả. Nhóm đã đầu tư nhiều vào tự động hóa, nhưng **thời gian chờ tăng mà chất lượng phản hồi không tăng tương ứng**.

Một nhóm khác chọn cách bỏ các test chậm khỏi pull request để pipeline xanh nhanh hơn. Sau vài tuần, lỗi tương thích database và lỗi retry chỉ được phát hiện sau khi hợp nhất. Họ đã giảm thời gian chạy, nhưng cũng giảm bằng chứng bảo vệ hệ thống.

Hai tình huống cho thấy tối ưu quy trình kiểm tra không đơn giản là **làm pipeline ngắn nhất có thể**. Cần cân bằng chi phí kiểm tra với giá trị của thông tin mà mỗi kiểm tra mang lại, đồng thời bảo vệ những hành vi và rủi ro quan trọng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Cổng chất lượng**, bài này trình bày cách **điều chỉnh quy trình khi chi phí kiểm tra vượt giá trị phản hồi**: đo đúng chi phí, phân tầng kiểm tra, lựa chọn theo phạm vi ảnh hưởng và rủi ro, cải thiện cách chạy, giữ kiểm tra toàn diện ở thời điểm phù hợp và xác minh rằng việc tối ưu không làm mất bằng chứng cần thiết.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện các thành phần chi phí của quy trình kiểm tra: thời gian chạy, thời gian chờ, tài nguyên CI, thời gian điều tra và bảo trì test.
- Phân biệt **kiểm tra chậm nhưng có giá trị cao** với kiểm tra tốn kém nhưng ít cung cấp thông tin hữu ích.
- Tổ chức các vòng phản hồi nhanh, trung gian và toàn diện theo mức rủi ro và phạm vi thay đổi.
- Dùng test impact analysis có giới hạn, biết khi nào phải mở rộng phạm vi hoặc chạy full suite.
- Áp dụng cache, parallelism, test sharding và cô lập dữ liệu mà không làm kết quả thiếu tin cậy.
- Theo dõi flaky tests, retry, thời gian phản hồi và lỗi lọt qua để đánh giá chất lượng của chính pipeline.
- Thiết kế quality gate và ngoại lệ có trách nhiệm, không âm thầm bỏ kiểm tra quan trọng để đạt mục tiêu thời gian.

## 1. Chi phí kiểm tra gồm nhiều thứ hơn thời gian chạy

Khi nói “pipeline quá chậm”, nhóm thường nhìn vào số phút của job. Nhưng chi phí thực tế còn có những thành phần khác:

| Thành phần | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| **Thời gian chạy (execution time)** | Unit suite, integration test, SAST mất bao lâu | Tăng lượng runner cần dùng và thời gian tới kết quả |
| **Thời gian chờ (queue time)** | Job chờ runner hoặc môi trường database | Developer chờ dù test chưa bắt đầu |
| **Thời gian phản hồi của người phát triển** | Chờ pipeline xong mới biết lỗi đơn giản | Làm gián đoạn tập trung và kéo dài vòng sửa |
| **Thời gian chẩn đoán** | Log khó đọc, test flaky, lỗi chỉ xảy ra trong suite lớn | Tăng công sức tìm nguyên nhân |
| **Chi phí bảo trì** | Fixture phức tạp, môi trường phụ thuộc, test trùng lặp | Mỗi lần đổi sản phẩm phải sửa nhiều test |
| **Chi phí hạ tầng** | Runner CPU/RAM, database tạm, artifact và cache | Tăng chi phí vận hành CI |
| **Chi phí lỗi lọt qua** | Bug phát hiện muộn, rollback, hỗ trợ khách hàng | Có thể lớn hơn nhiều so với chi phí kiểm tra trước đó |

Vì vậy, một pipeline chạy 15 phút chưa chắc rẻ hơn pipeline chạy 25 phút. Nếu pipeline 15 phút thường flaky và cần 20 phút điều tra, tổng chi phí có thể cao hơn. Ngược lại, một kiểm tra hiệu năng kéo dài 40 phút có thể rất đáng giữ trước khi phát hành hệ thống thanh toán có rủi ro lớn.

### Giá trị phản hồi đến từ điều gì?

Một kiểm tra có giá trị khi nó:

- Phát hiện một lớp lỗi mà các kiểm tra khác khó phát hiện.
- Phản hồi đủ sớm để sửa lỗi ở nơi tạo ra thay đổi.
- Cho biết vị trí, điều kiện và nguyên nhân đủ rõ để chẩn đoán.
- Bảo vệ hợp đồng quan trọng hoặc giảm rủi ro có tác động lớn.
- Có kết quả ổn định, có thể tái lập và được nhóm tin cậy.

Một test chạy rất nhanh nhưng assertion không kiểm tra điều gì có giá trị thấp. Một test chậm nhưng phát hiện được lỗi migration phá dữ liệu có thể có giá trị cao. **Không nên xếp hạng test chỉ bằng số giây chạy.**

## 2. Xác định thời gian phản hồi mục tiêu

Nhóm cần xác định **thời điểm nào cần nhận loại thông tin nào**. Không phải mọi kết quả đều phải có trong vài giây, nhưng những lỗi đơn giản nên được phát hiện sớm.

Một cách phân tầng tham khảo:

| Vòng kiểm tra | Thời điểm | Ví dụ | Mục tiêu phản hồi |
| --- | --- | --- | --- |
| **Local fast feedback** | Trong lúc lập trình | Format, compile, unit test nhỏ, lint nhanh | Vài giây đến vài phút tùy dự án |
| **Pull request fast gate** | Khi mở/cập nhật PR | Build, unit suite liên quan, kiểm tra mã mới | Sớm đủ để tác giả sửa trước khi review sâu |
| **PR extended checks** | Trước merge hoặc theo mức rủi ro | Integration, contract, SAST/SCA, migration test | Chấp nhận lâu hơn nếu bằng chứng cần thiết |
| **Full regression** | Theo lịch, trước release hoặc sau thay đổi rộng | Full suite, compatibility, end-to-end | Toàn diện hơn, không cần chạy sau mọi lần lưu |
| **Performance/resilience** | Theo lịch, trước release hoặc thay đổi hạ tầng | Load, stress, failover, chaos ở môi trường an toàn | Phục vụ quyết định về tải và khả năng phục hồi |
| **Post-deploy verification** | Staging/canary/production | Smoke, telemetry, đối soát, health checks | Phát hiện sai lệch sau triển khai |

Các mốc thời gian cụ thể cần dựa trên năng lực runner, kích thước dự án và nhu cầu của nhóm. Bảng này là **mô hình phân tầng**, không phải cam kết rằng mọi dự án phải đạt một ngưỡng phút cố định.

### Vòng nhanh không thay thế vòng toàn diện

Nếu chỉ chạy unit test liên quan tới file vừa sửa, có thể bỏ sót:

- Caller khác sử dụng cùng API.
- Dependency được nạp qua reflection hoặc dependency injection.
- Thay đổi schema ảnh hưởng service khác.
- Serializer/event contract dùng chung.
- Cấu hình, permission hoặc resource được chọn lúc runtime.

Vì thế, test chọn lọc phải có **quy tắc mở rộng phạm vi và fallback**. Full suite vẫn cần chạy theo lịch, trước phát hành hoặc khi thay đổi có ảnh hưởng rộng.

~~~text
              THAY ĐỔI MÃ
                  |
                  v
           Xác định phạm vi
                  |
                  v
       Local fast checks / unit
                  |
                  v
       PR checks theo ảnh hưởng
                  |
          +-------+-------+
          |               |
     Phạm vi rõ       Phạm vi rộng,
     và rủi ro thấp   mơ hồ hoặc nhạy cảm
          |               |
          v               v
   Test liên quan      Mở rộng suite /
   + contract          full regression
          |               |
          +-------+-------+
                  |
                  v
         Gate theo rủi ro
                  |
                  v
       Full / release / vận hành
~~~

## 3. Chọn kiểm tra theo phạm vi thay đổi và rủi ro

**Test impact analysis** tìm các bài test có khả năng bị ảnh hưởng bởi một thay đổi, dựa trên quan hệ giữa tệp, module, dependency, API và test. Cách này có thể giảm thời gian chạy, nhưng chỉ an toàn khi đồ thị phụ thuộc và quy tắc lựa chọn đủ đáng tin.

### Những thay đổi có thể chạy phạm vi hẹp

- Sửa một hàm thuần, không đổi chữ ký hoặc dependency bên ngoài.
- Sửa thông báo hiển thị không ảnh hưởng logic hoặc hợp đồng.
- Sửa tài liệu hoặc comment không được dùng làm đầu vào sinh mã.
- Thay đổi trong module có ranh giới và test mapping rõ.

Ngay cả những trường hợp này vẫn cần compile và các kiểm tra cơ bản đã được nhóm quy định.

### Những thay đổi nên mở rộng phạm vi

| Loại thay đổi | Vì sao cần test rộng hơn? |
| --- | --- |
| Public API hoặc event schema | Caller và consumer khác có thể bị ảnh hưởng |
| Database schema, query, transaction | Dữ liệu cũ, isolation và migration có thể thay đổi hành vi |
| Authentication/authorization | Quyền truy cập đi qua nhiều endpoint và tenant |
| Serialization, reflection, DI | Quan hệ sử dụng không phải lúc nào cũng thấy qua import trực tiếp |
| Shared library hoặc domain model | Nhiều module phụ thuộc vào cùng hợp đồng |
| Build script, compiler, plugin | Phạm vi build/test có thể thay đổi toàn dự án |
| Retry, cache, concurrency | Lỗi phụ thuộc thời gian và trạng thái chia sẻ |
| Dependency có advisory hoặc nâng major version | API, hành vi runtime và rủi ro bảo mật có thể đổi |

### Khi nào không nên tin vào test selection?

Hãy mở rộng sang full suite nếu:

- Đồ thị dependency chưa đầy đủ hoặc chưa được kiểm chứng.
- Mã dùng reflection, dynamic dispatch, plugin hoặc tên lớp/cấu hình sinh lúc runtime.
- Có thay đổi ở interface dùng chung nhưng không xác định đủ consumer.
- Test trước đó từng phát hiện lỗi ngoài phạm vi mà bộ chọn đã dự đoán.
- Một module nhạy cảm có hậu quả cao, dù diff chỉ nhỏ.
- Bộ chọn không xác định được tác động hoặc metadata không nhất quán.

**Không xác định được phạm vi không có nghĩa là không có tác động.** Với rủi ro cao, lựa chọn an toàn là chạy rộng hơn hoặc yêu cầu review chuyên môn.

### Hiệu chỉnh test selection bằng full run

Nếu nhóm dùng test impact analysis, nên định kỳ so sánh:

1. Tập test mà bộ chọn đề xuất.
2. Tập test thực sự chạy trong full suite.
3. Những lỗi chỉ xuất hiện trong test bị bỏ qua.
4. Thay đổi dependency hoặc cấu hình khiến quan hệ tác động thay đổi.

Nếu full run phát hiện lỗi trong một test đã bị bộ chọn loại, cần điều tra **vì sao đồ thị tác động bỏ sót**, sửa mapping hoặc mở rộng chính sách. Không chỉ thêm một ngoại lệ thủ công cho đúng một test rồi tiếp tục dùng bộ chọn chưa đáng tin.

## 4. Ví dụ Java: phân loại test để có phản hồi phù hợp

Giả sử dự án Java có chính sách phí giao hàng. Unit test tính phí không cần database; kiểm tra caller và repository cần tích hợp; kiểm thử tải cần môi trường riêng.

JUnit 5 cho phép gắn **tag** để phân loại test. Tag là metadata; bản thân annotation không tự tạo pipeline hay quyết định test nào được chạy.

### Unit test nhanh

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("fast")
class DeliveryFeePolicyTest {
    private final DeliveryFeePolicy policy = new DeliveryFeePolicy();

    @Test
    void standardDeliveryIsFreeAtThreshold() {
        assertEquals(
            0,
            policy.calculateFee(500_000, DeliveryType.STANDARD)
        );
    }

    @Test
    void expressDeliveryKeepsItsFeeAboveThreshold() {
        assertEquals(
            30_000,
            policy.calculateFee(600_000, DeliveryType.EXPRESS)
        );
    }
}
~~~

### Integration test chậm hơn

Một `CheckoutFeeIntegrationTest` có thể được gắn `@Tag("integration")` và dùng fixture của dự án để:

1. Khởi tạo database test với schema đúng phiên bản.
2. Tạo đơn giao STANDARD có tổng tiền 500.000 VND.
3. Gọi luồng checkout qua service và adapter thật.
4. Đọc bản ghi đã lưu, xác nhận phí giao hàng bằng 0 và trạng thái đơn đúng hợp đồng.
5. Dọn dữ liệu/tài nguyên sau test để những lần chạy song song không ảnh hưởng nhau.

Đây là mô tả mục tiêu của integration test, không phải mã triển khai fixture. Dự án có thể dùng test container hoặc môi trường tích hợp phù hợp; điều quan trọng là test đi qua **ranh giới cần kiểm chứng** thay vì chỉ gọi lại hàm chính sách thuần.

### Chọn nhóm test trong pipeline

Với Gradle hoặc Maven, cách lọc theo tag cần được cấu hình trong build. Ví dụ các lệnh khái niệm:

~~~bash
# Ví dụ Gradle: chạy task/unit test đã cấu hình chỉ nhận tag fast
./gradlew test -PtestGroup=fast

# Ví dụ Maven: chạy profile đã cấu hình cho nhóm integration
./mvnw verify -Pintegration
~~~

Các tham số `testGroup` và profile `integration` ở đây **là ví dụ tên cấu hình**, không phải tùy chọn mặc định của Gradle/Maven. Dự án phải khai báo task/profile tương ứng, cách include/exclude tag và cách tổng hợp kết quả. Nếu không có cấu hình, việc thêm `@Tag("fast")` không tự làm cho lệnh build chạy ít test hơn.

## 5. Tối ưu bằng song song hóa và chia nhóm test

**Parallel execution** cho phép chạy các job hoặc test độc lập cùng lúc. **Sharding** chia một tập test thành nhiều phần để chạy trên các runner khác nhau.

Ví dụ, 300 test độc lập có thể được chia thành ba nhóm theo thời gian ước lượng. Nhưng lợi ích chỉ có khi các test **không tranh chấp tài nguyên dùng chung** hoặc đã được cô lập.

### Điều kiện để parallelism có ích

- Mỗi test có dữ liệu riêng hoặc cơ chế phân vùng dữ liệu.
- Test không phụ thuộc thứ tự thực thi.
- File, port, queue, database schema và tài khoản dùng chung được cô lập.
- Không dùng biến static mutable hoặc singleton chứa trạng thái test không kiểm soát.
- Test có timeout hợp lý và dọn tài nguyên khi thất bại.
- Log có đủ thông tin nhận diện shard/test để điều tra.

Nếu hai test cùng cập nhật một bản ghi hoặc dùng chung một thư mục tạm, chạy song song có thể tạo flaky tests. Khi đó tăng số runner đôi khi làm pipeline **chậm hơn và kém tin cậy hơn**.

### Sharding không được bỏ sót test

Nếu chia test theo tên lớp hoặc hash, cần xác minh:

- Mọi test bắt buộc được gán vào đúng một shard.
- Khi thêm/xóa/đổi tên test, phân phối được cập nhật.
- Test thất bại ở shard nào có thể truy vết và chạy lại riêng.
- Kết quả tổng hợp chỉ đạt khi **tất cả shard bắt buộc** đạt.
- Timeout hoặc runner mất kết nối được phân biệt với test đã chạy thành công.

Đừng đánh đồng “không có kết quả” với “pass”.

## 6. Dùng cache để giảm việc lặp lại, không làm mất tính tái lập

Cache dependency, build output hoặc test fixture có thể giảm thời gian CI, nhưng cache cần có khóa và điều kiện vô hiệu hóa phù hợp.

| Loại cache | Khóa hoặc điều kiện nên xét | Rủi ro nếu cấu hình sai |
| --- | --- | --- |
| Dependency cache | Lockfile, wrapper, repository và nền tảng | Dùng dependency không đúng phiên bản hoặc artifact cũ |
| Build cache | Input của task, compiler, plugin và biến môi trường liên quan | Dùng output sinh từ đầu vào khác |
| Docker/image cache | Base image, package lock, build definition | Image không tương ứng cấu hình mới |
| Test data cache | Phiên bản schema, dữ liệu fixture, test code | Dữ liệu cũ làm test xanh giả hoặc gây phụ thuộc chéo |
| Analysis cache | Commit, rule set, phạm vi và phiên bản analyzer | Bỏ qua finding mới do cache không hợp lệ |

Một nguyên tắc an toàn là **cache chỉ tối ưu công việc có thể tái tạo; nó không được trở thành nguồn sự thật duy nhất**. Khi nghi ngờ cache sai, cần có cách chạy clean hoặc invalidate để so sánh.

Với dependency, dùng lockfile hoặc cơ chế pin phiên bản phù hợp giúp local và CI tải cùng tập thư viện. Với build cache, cần bảo đảm task khai báo đầy đủ input/output; nếu task đọc biến môi trường nhưng không khai báo input, cache có thể trả kết quả cũ.

## 7. Giảm thời gian chẩn đoán, không chỉ giảm thời gian chạy

Một test thất bại có giá trị thấp nếu log chỉ ghi `FAILED` mà không chỉ ra điều kiện. Nhóm có thể cải thiện:

- In rõ expected/actual, input và tên kịch bản.
- Lưu log, trace, artifact và phiên bản môi trường có liên quan.
- Chia test theo suite/module để khoanh vùng nhanh.
- Báo cáo test thất bại đầu tiên và những test bị bỏ qua vì dependency.
- Dùng định danh dữ liệu duy nhất và trace ID cho test tích hợp.
- Phân biệt lỗi sản phẩm, lỗi test, lỗi môi trường và lỗi runner.
- Giữ lịch sử retry, không ghi đè kết quả thất bại ban đầu.

Ví dụ:

~~~text
Test: standardDeliveryIsFreeAtThreshold
Commit: <commit-id>
Input: subtotal=500000, type=STANDARD
Expected: fee=0
Actual: fee=20000
Environment: JDK, OS, timezone, build revision
Result: FAILED
~~~

Thông tin này giúp nhóm nhận ra lỗi điều kiện ngưỡng nhanh hơn nhiều so với một dòng “unit suite failed”. Tuy nhiên, không ghi secret, dữ liệu cá nhân hoặc nội dung nhạy cảm vào artifact test.

## 8. Flaky tests và retry: đừng mua thời gian bằng cách mất niềm tin

Test không ổn định có thể thất bại rồi xanh khi chạy lại mà không có thay đổi mã. Nguyên nhân thường gặp:

- Phụ thuộc đồng hồ thực, timezone hoặc locale mặc định.
- Chia sẻ database, file hoặc trạng thái static giữa test.
- Chờ bằng `Thread.sleep()` thay vì chờ tín hiệu hoàn thành.
- Dùng mạng hoặc dịch vụ ngoài không được kiểm soát.
- Phụ thuộc thứ tự chạy hoặc scheduling.
- Timeout quá sát hoặc tài nguyên runner thiếu ổn định.

Retry có thể giúp xác định một lỗi tạm thời, nhưng **một test xanh sau retry không xóa kết quả đỏ đầu tiên**.

### Chính sách retry có trách nhiệm

1. Lưu kết quả và log lần chạy đầu.
2. Retry giới hạn trong những tình huống được quy định, không lặp vô hạn.
3. Phân loại lỗi hạ tầng và lỗi test/sản phẩm bằng bằng chứng.
4. Nếu test có flaky behavior, mở công việc sửa với owner và thời hạn.
5. Nếu phải quarantine, ghi phạm vi, lý do, rủi ro và điều kiện gỡ.
6. Không cho phép test quan trọng bị quarantine vô thời hạn mà không có quyết định chấp nhận rủi ro.

Với kiểm thử thanh toán, quyền truy cập hoặc migration, cần đánh giá kỹ trước khi tạm bỏ gate. Có thể dùng kiểm tra thay thế hoặc hạn chế phát hành, nhưng không nên giả định retry nhiều lần sẽ làm kết quả đáng tin.

## 9. Đánh giá giá trị của một kiểm tra

Để quyết định giữ, chuyển tầng, tối ưu hay loại bỏ một test, hãy đặt câu hỏi:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Khả năng phát hiện** | Test có phát hiện lớp lỗi cụ thể mà test khác khó phát hiện không? |
| **Tác động nếu bỏ** | Nếu không chạy test này trước merge/release, hậu quả có thể là gì? |
| **Tần suất liên quan** | Thành phần này thay đổi hoặc được sử dụng thường xuyên tới đâu? |
| **Độ ổn định** | Kết quả có lặp lại được trong điều kiện giống nhau không? |
| **Khả năng chẩn đoán** | Khi thất bại, có xác định được nguyên nhân không? |
| **Chi phí toàn phần** | Thời gian chạy, queue, bảo trì, môi trường và công điều tra là bao nhiêu? |
| **Tính duy nhất** | Test có bảo vệ một hợp đồng chưa được kiểm tra ở nơi khác không? |
| **Mức tin cậy** | Expected có độc lập với implementation và có nguồn từ yêu cầu không? |

### Ma trận quyết định minh họa

| Giá trị phát hiện | Chi phí thấp | Chi phí cao |
| --- | --- | --- |
| **Cao** | Giữ trong vòng nhanh nếu phù hợp | Tối ưu cách chạy hoặc chuyển sang vòng rộng hơn; giữ trước mốc phát hành cần thiết |
| **Thấp** | Xem xét gộp, loại bỏ hoặc cải thiện assertion nếu trùng lặp | Điều tra test có còn cần thiết, có flaky hay đang bảo vệ rủi ro hiếm nhưng lớn |

Không được quyết định chỉ bằng ma trận. Một kiểm tra hiếm khi phát hiện lỗi nhưng lỗi đó có thể làm mất dữ liệu hoặc vi phạm quyền truy cập thì vẫn có giá trị cao. Cần xét **tác động và mức rủi ro**, không chỉ tần suất test đỏ.

## 10. Đo hiệu quả tối ưu quy trình

Sau khi thay đổi pipeline, đo trước và sau bằng định nghĩa nhất quán:

| Chỉ số | Ý nghĩa | Cần thận trọng |
| --- | --- | --- |
| **Feedback latency p50/p95** | Thời gian tới kết quả ở mức trung vị và nhóm chạy chậm | Đừng chỉ báo trung bình nếu có job rất chậm |
| **Queue time** | Thời gian chờ runner | Có thể là vấn đề hạ tầng chứ không phải test |
| **Execution time** | Thời gian job thực chạy | Song song hóa có thể giảm wall-clock nhưng tăng runner-minutes |
| **Runner-minutes / PR** | Tài nguyên CI tiêu thụ | Cần tính cả retry và job thất bại |
| **Flaky rate** | Tỷ lệ test có kết quả không ổn định theo định nghĩa của nhóm | Cần phân biệt test flaky và lỗi hạ tầng |
| **Mean time to diagnose** | Thời gian xác định nguyên nhân sau thất bại | Phụ thuộc chất lượng log và phân loại |
| **Escaped defects** | Lỗi phát hiện sau mốc gate/phát hành | Cần mẫu số, mức sử dụng và cách phát hiện |
| **Gate bypass / quarantine** | Mức độ ngoại lệ trong quy trình | Số thấp không đảm bảo ngoại lệ đều hợp lý |

Ví dụ số liệu minh họa:

| Chỉ số | Trước tối ưu | Sau tối ưu |
| --- | ---: | ---: |
| PR feedback p50 | 32 phút | 14 phút |
| PR feedback p95 | 58 phút | 29 phút |
| Runner-minutes / PR | 74 | 62 |
| Flaky test rate | 4,0% | 1,5% |
| Full suite trước release | Có | Có |
| Test tích hợp về quyền truy cập | Có | Có |

Các số liệu này chỉ minh họa cách báo cáo. Trước khi kết luận cải tiến thành công, cần xác nhận cùng phạm vi PR, cấu hình runner, định nghĩa flaky, số lần chạy và loại test bắt buộc. Nếu sau tối ưu nhóm bỏ integration test, thời gian giảm không phải bằng chứng quy trình tốt hơn.

### Phản hồi nhanh hơn có thể đi cùng tổng chi phí cao hơn

Giả sử nhóm chuyển một test dài sang chạy ở mỗi PR trên nhiều runner song song. Wall-clock giảm, nhưng runner-minutes và chi phí hạ tầng tăng. Đây có thể vẫn là quyết định tốt nếu giảm đáng kể thời gian chờ của nhiều người và giữ được bằng chứng cần thiết. Nhưng phải công bố cả hai chiều.

Ngược lại, chỉ chạy test chọn lọc có thể giảm runner-minutes nhưng làm tăng rủi ro bỏ sót dependency. Cần theo dõi lỗi phát hiện bởi full suite hoặc sau merge để hiệu chỉnh lựa chọn.

## 11. Chuyển test giữa các vòng mà không hạ mức bảo vệ

Không phải cứ test chậm là nên xóa. Có thể:

- Chuyển test end-to-end trùng lặp xuống một số contract/integration test có phạm vi nhỏ hơn, nếu các hợp đồng được bảo vệ đầy đủ.
- Giữ một số test smoke đại diện ở PR, chạy full end-to-end theo lịch hoặc trước release.
- Chạy performance test trên môi trường chuyên biệt khi thay đổi liên quan tới hiệu năng hoặc trước mốc phát hành.
- Chạy full SAST/SCA theo lịch, đồng thời giữ kiểm tra nhanh trên phần mã mới và dependency thay đổi.
- Tách test migration vào suite riêng và bắt buộc chạy khi schema hoặc query liên quan thay đổi.
- Chạy test theo module và dependency graph, nhưng fallback full suite khi tác động không xác định.

Việc chuyển tầng chỉ hợp lý nếu **giá trị bảo vệ không biến mất ở mốc cần thiết**. Nếu một test bảo vệ quy tắc phân quyền trên endpoint công khai bị chuyển sang chạy mỗi đêm, có thể tồn tại một khoảng thời gian dài giữa merge và phát hiện lỗi. Cần đánh giá rủi ro của khoảng trống đó.

### Test trùng lặp có thể được thay thế bằng test nhỏ hơn

Nhiều end-to-end tests có thể đi qua cùng một logic và chỉ khác dữ liệu đầu vào. Nếu chúng đều thất bại vì cùng một quy tắc nhỏ, có thể chuyển một phần kiểm tra sang unit/contract test và giữ số ít end-to-end tests để bảo vệ đường tích hợp. Nhưng chỉ nên làm khi:

- Unit/contract tests thực sự kiểm tra hợp đồng cần bảo vệ.
- Các adapter và đường gọi quan trọng vẫn có integration coverage.
- Không bỏ mất hành vi phát sinh từ cấu hình, auth, transaction hoặc serialization.
- Kết quả sau chuyển đổi được review và so sánh với bộ test cũ trong phạm vi phù hợp.

**Không được dùng test pyramid như luật cứng** để ép mọi hệ thống có số unit test lớn hơn integration test. Kiến trúc và rủi ro quyết định phân bổ hợp lý.

## 12. Quality gate sau tối ưu

Một gate hiệu quả nên nói rõ:

1. **Kiểm tra nào bắt buộc với mọi PR?** Ví dụ compile, unit suite nền tảng, secret scan và review.
2. **Điều kiện nào kích hoạt kiểm tra rộng?** Schema, public API, auth, concurrency, dependency, build configuration.
3. **Kiểm tra nào bắt buộc trước release?** Full regression, migration, performance hoặc resilience tùy hệ thống.
4. **Kết quả nào chặn merge?** Test bắt buộc thất bại, finding đã xác nhận ở mức rủi ro quy định, thiếu review.
5. **Ngoại lệ được quyết định bởi ai?** Chủ sở hữu hệ thống hoặc người có thẩm quyền theo quy trình.
6. **Ngoại lệ hết hạn khi nào?** Có ticket, owner, biện pháp thay thế và mốc xem lại.

### Ví dụ chính sách minh họa

| Tình huống | Kiểm tra/gate |
| --- | --- |
| Sửa hàm thuần trong module nhỏ | Format, compile, unit test liên quan và suite module |
| Đổi public API | Unit + contract test cho caller/consumer, compatibility review |
| Đổi schema hoặc query | Migration/integration test trên database phù hợp |
| Đổi authentication/authorization | Test quyền âm/dương qua ranh giới HTTP và repository |
| Đổi retry/transaction/concurrency | Test trạng thái lỗi, retry, idempotency và tranh chấp |
| Đổi build tool hoặc dependency nền tảng | Full build, dependency/security checks và suite rộng |
| Chuẩn bị release | Full regression và các kiểm tra chuyên biệt theo rủi ro |

Chính sách phải được ghi thành **required checks và quy tắc branch protection** ở nền tảng repository. Nếu chỉ ghi trong tài liệu nhưng hệ thống vẫn cho merge khi job bắt buộc thất bại, gate không được thực thi.

## 13. Ngoại lệ khi chi phí kiểm tra thực sự vượt khả năng

Đôi khi một dịch vụ ngoài không sẵn sàng, runner thiếu tài nguyên hoặc môi trường kiểm thử chưa thể tái tạo. Nhóm có thể cần một ngoại lệ tạm thời, nhưng phải quản lý nó như **một rủi ro được chấp nhận**, không phải kết quả pass.

Ghi nhận tối thiểu:

| Trường | Cần ghi |
| --- | --- |
| Kiểm tra bị miễn | Tên job/test/rule và commit cụ thể |
| Nguyên nhân | Bằng chứng lỗi môi trường hoặc chi phí bất thường |
| Phạm vi chưa kiểm tra | Hành vi, adapter hoặc rủi ro nào còn thiếu bằng chứng |
| Người chấp thuận | Chủ sở hữu có quyền quyết định |
| Biện pháp thay thế | Test khác, review chuyên môn, staging hoặc giới hạn rollout |
| Thời hạn | Ngày hoặc điều kiện phải xem lại |
| Hành động khắc phục | Owner và ticket cụ thể |

Không nên miễn một kiểm tra có tác động cao chỉ vì nó làm chậm PR. Có thể điều chỉnh lịch chạy, cải thiện môi trường hoặc chia test; nếu không có bằng chứng thay thế, cần cân nhắc trì hoãn merge/release.

## 14. Quy trình điều chỉnh khi pipeline trở nên quá đắt

Một vòng cải tiến có thể thực hiện theo thứ tự:

1. **Lập baseline:** đo p50/p95 feedback, queue time, execution time, runner-minutes, flaky rate và loại lỗi đang được phát hiện.
2. **Xác định nút thắt:** job nào chiếm nhiều thời gian, test nào flaky, runner chờ lâu hay môi trường setup tốn kém?
3. **Đánh giá giá trị:** test đó bảo vệ hợp đồng gì, có lớp test nào khác kiểm tra tương đương không, lỗi bỏ sót có tác động gì?
4. **Chọn biện pháp:** tối ưu fixture, cache, parallelism, sharding, test selection, phân tầng hoặc cải thiện log.
5. **Giữ đường lui:** có clean run/full suite và cách fallback khi test selection không chắc chắn.
6. **Thử trên phạm vi nhỏ:** so sánh cùng loại PR, cùng cấu hình và thời gian quan sát phù hợp.
7. **Kiểm tra tác dụng phụ:** runner-minutes, flakiness, lỗi lọt qua, gate bypass và chất lượng chẩn đoán có xấu đi không?
8. **Điều chỉnh chính sách:** giữ thay đổi có lợi; hoàn tác nếu thời gian giảm nhưng rủi ro hoặc chi phí điều tra tăng.
9. **Ghi nhận:** cập nhật owner, định nghĩa metric, lịch full suite và các ngoại lệ còn hiệu lực.

Không nên thay đổi nhiều yếu tố cùng lúc nếu nhóm muốn biết yếu tố nào thực sự tạo ra khác biệt. Ví dụ vừa chuyển integration tests, vừa thay runner, vừa nâng JDK khiến việc so sánh trước–sau khó giải thích.

## 15. Bài tập tình huống

Một nhóm có pipeline PR với kết quả trung bình như sau:

| Job | Thời gian chạy | Tỷ lệ thất bại đầu tiên | Ghi chú |
| --- | ---: | ---: | --- |
| Format + compile | 2 phút | 3% | Lỗi thường được phát hiện local |
| Unit suite | 7 phút | 8% | Có test giá trị biên quan trọng |
| Integration suite | 24 phút | 5% | Một số test database flaky |
| Full end-to-end | 31 phút | 1% | Nhiều test đi qua cùng logic checkout |
| SAST + SCA | 10 phút | 2% | Có finding cần triage theo rủi ro |

Nhóm đề xuất bỏ integration suite và full end-to-end khỏi PR, chỉ chạy nightly để rút thời gian phản hồi.

**Câu hỏi A.** Có thể chấp nhận đề xuất này chỉ dựa trên tổng thời gian 74 phút không? Vì sao?

**Câu hỏi B.** Những kiểm tra nào nên giữ trong vòng PR, và điều kiện nào cần kích hoạt suite rộng hơn?

**Câu hỏi C.** Nên điều tra gì trước khi kết luận integration suite có chi phí cao vì test kém chất lượng?

**Câu hỏi D.** Làm sao giảm thời gian end-to-end mà vẫn giữ bằng chứng bảo vệ checkout?

**Câu hỏi E.** Đề xuất bộ chỉ số để đánh giá thay đổi pipeline sau một giai đoạn thử nghiệm.

### Gợi ý đáp án

**A.** Chưa thể. Tổng thời gian không cho biết job chạy tuần tự hay song song, queue time, runner-minutes, lớp lỗi mỗi suite phát hiện và tác động nếu bỏ. Integration test database có thể đang bảo vệ migration/transaction; end-to-end có thể là bằng chứng duy nhất cho một số đường checkout. Cần đánh giá giá trị trước khi chuyển tầng.

**B.** Giữ format/compile, unit suite và những kiểm tra nhanh có giá trị cao; SAST/SCA nên giữ phần phù hợp với mã/dependency mới theo chính sách. Integration tests cần chạy khi thay đổi database, transaction, adapter hoặc checkout; full end-to-end có thể chạy ở một tập đại diện trước merge và full suite theo lịch/release, nếu hợp đồng quan trọng vẫn được bảo vệ tại mốc cần thiết.

**C.** Xem test nào flaky, fixture có dùng chung database không, setup có lặp, dữ liệu có cô lập, log có đủ thông tin, runner có thiếu tài nguyên và phiên bản database có nhất quán không. Tách lỗi hạ tầng khỏi lỗi sản phẩm trước khi loại test.

**D.** Xác định end-to-end test nào thực sự kiểm tra hợp đồng xuyên tầng; chuyển một số tổ hợp sang unit/contract/integration tests có oracle độc lập; giữ test đại diện cho luồng checkout chính và các ranh giới quan trọng. Chỉ giảm tập end-to-end sau khi review phạm vi bằng chứng còn lại.

**E.** Đo feedback p50/p95, queue time, execution time, runner-minutes/PR, flaky rate, thời gian chẩn đoán, số lần retry, gate bypass và lỗi checkout phát hiện sau merge trên số giao dịch phù hợp. Ghi cùng phạm vi PR, cấu hình runner, kỳ quan sát và giới hạn mẫu để diễn giải.

## Ghi nhớ

**Điều chỉnh quy trình kiểm tra là tối ưu chi phí để nhận được phản hồi có giá trị, không phải loại bỏ kiểm tra chậm bằng mọi giá.** Vòng local nên bắt lỗi nhanh; pre-merge giữ các bằng chứng cần thiết cho thay đổi; full regression, kiểm thử chuyên biệt và quan sát sau triển khai bảo vệ những rủi ro rộng hơn.

Hãy đo cả thời gian chờ, tài nguyên, độ ổn định và lỗi lọt qua; chọn test theo phạm vi ảnh hưởng và hậu quả; tối ưu bằng cache, song song hóa, sharding hoặc test selection chỉ khi kết quả vẫn đáng tin. Khi phạm vi chưa rõ hoặc rủi ro cao, mở rộng kiểm tra. **Pipeline tốt không chỉ chạy nhanh hơn: nó giúp nhóm nhận đúng thông tin sớm hơn mà vẫn giữ được bằng chứng cần thiết để thay đổi phần mềm an toàn.**
