# Thứ tự phản hồi từ kiểm tra nhanh đến kiểm tra tốn kém

Một pull request chỉ đổi điều kiện miễn phí giao hàng có thể phải chờ 25 phút vì pipeline chạy kiểm thử end-to-end trước khi phát hiện mã không biên dịch. Ở một pipeline khác, formatter báo lỗi sau vài giây, giúp tác giả sửa ngay khi ngữ cảnh còn mới. Cả hai pipeline có thể dùng cùng bộ kiểm tra, nhưng **thứ tự phản hồi quyết định nhóm phát hiện vấn đề sớm đến đâu và tốn bao nhiêu thời gian để hiểu nguyên nhân**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Cổng chất lượng**, một quality gate đặt ra điều kiện để thay đổi được tiếp tục, tích hợp hoặc phát hành. Các kiểm tra nên được tổ chức để **phản hồi nhanh cho lỗi đơn giản, sau đó mở rộng dần sang kiểm chứng tốn kém và gần môi trường thực tế hơn**.

Bài học giải thích cách sắp xếp các bước, cách chọn điều kiện chặn merge, khi nào nên chạy song song và cách tránh một pipeline chậm nhưng vẫn bỏ sót rủi ro quan trọng.

## 1. Quality gate là gì?

**Quality gate (cổng chất lượng)** là một điểm kiểm soát trong quy trình phát triển. Nó đánh giá một hoặc nhiều tiêu chí đã thống nhất và quyết định thay đổi có được chuyển sang bước tiếp theo hay không.

Ví dụ một pull request có thể cần:

- Mã được format theo cấu hình của repository.
- Mã biên dịch thành công.
- Unit test bắt buộc đạt.
- Không có lỗi phân tích tĩnh nghiêm trọng.
- Không có secret bị đưa vào source.
- Không có lỗ hổng dependency vượt mức rủi ro đã đặt.
- Các integration/contract test liên quan đạt.
- Reviewer đã xác nhận thay đổi phù hợp với yêu cầu.

Một gate có thể là:

- **Blocking:** thất bại thì không được merge hoặc phát hành cho đến khi xử lý hay có quyết định chấp nhận rủi ro đúng thẩm quyền.
- **Advisory:** cung cấp tín hiệu hoặc cảnh báo để nhóm xem xét, nhưng không tự động chặn.
- **Conditional:** chỉ áp dụng khi thay đổi chạm một vùng, loại file, thành phần hoặc mức rủi ro nhất định.

Không phải mọi cảnh báo đều nên chặn. Nếu gate chặn vì hàng trăm vấn đề không liên quan hoặc false positive chưa được xử lý, nhóm có thể mất niềm tin vào pipeline và tìm cách bỏ qua nó.

**Một quality gate tốt có tiêu chí rõ, kết quả có thể giải thích, owner xử lý và hành động tiếp theo cụ thể.**

## 2. Vì sao nên phản hồi từ kiểm tra nhanh đến kiểm tra tốn kém?

Một pipeline thường có nhiều loại kiểm tra với chi phí khác nhau:

- **Nhanh:** kiểm tra định dạng, whitespace, cú pháp cấu hình, secret đơn giản, compile hoặc kiểm tra một module nhỏ.
- **Trung bình:** unit test, phân tích tĩnh, kiểm tra dependency, component test.
- **Tốn kém hơn:** integration test với dịch vụ phụ thuộc, contract test trong môi trường triển khai, end-to-end, performance/load test và kiểm thử thủ công chuyên sâu.

Nếu một lỗi có thể được phát hiện trong 5 giây, không có lý do hợp lý để bắt tác giả đợi 20 phút trước khi thấy lỗi đó. Phát hiện sớm giúp:

1. **Giảm thời gian chờ:** tác giả nhận tín hiệu khi ngữ cảnh thay đổi còn mới.
2. **Giảm chi phí chạy:** không tiêu tốn tài nguyên cho các bước phụ thuộc vào một bản build đã lỗi.
3. **Dễ xác định nguyên nhân:** một lỗi đơn giản không bị lẫn với hàng loạt kết quả từ môi trường tích hợp.
4. **Tăng tốc vòng lặp sửa:** sửa xong có thể chạy lại kiểm tra liên quan ngay.
5. **Giữ tài nguyên CI:** worker và môi trường kiểm thử được dành cho thay đổi có khả năng đi tiếp.

Đây là nguyên tắc **fail fast (phát hiện và phản hồi sớm)**. Tuy nhiên, fail fast không có nghĩa mọi kiểm tra phải chạy tuần tự hoặc dừng ngay khi có bất kỳ lỗi nhỏ nào. Các kiểm tra độc lập có thể chạy song song để tiết kiệm thời gian, và một số kết quả hữu ích vẫn nên được thu thập ngay cả khi một bước khác thất bại.

## 3. Thứ tự tham khảo từ nhanh đến tốn kém

Một chuỗi kiểm tra điển hình cho pull request Java:

~~~mermaid
flowchart TD
    A["Checkout source và xác định phạm vi diff"] --> B["Format, whitespace, cấu hình và secret"]
    B --> C["Compile / type checking"]
    C --> D["Unit test nhanh"]
    D --> E["Static analysis và coverage gate"]
    E --> F["Dependency / license / security checks"]
    F --> G["Component, integration và contract tests"]
    G --> H["Deploy môi trường kiểm thử"]
    H --> I["End-to-end và smoke tests"]
    I --> J["Performance / load / resilience khi phù hợp"]
    J --> K["Review và quyết định merge / release"]
~~~

Đây là **thứ tự tư duy**, không phải công thức cứng cho mọi dự án. Có thể điều chỉnh theo dependency giữa các bước và rủi ro của thay đổi:

| Tầng | Kiểm tra điển hình | Mục tiêu phản hồi | Chi phí tương đối |
| --- | --- | --- | --- |
| 1 | Format, whitespace, cấu hình, secret scan nhanh | Bắt lỗi cơ học và dữ liệu nhạy cảm bị commit. | Thấp |
| 2 | Compile, type checking, schema/config validation | Xác nhận mã và cấu hình có thể được xử lý. | Thấp đến vừa |
| 3 | Unit test | Kiểm chứng logic nhỏ và các trường hợp biên. | Thấp đến vừa |
| 4 | Static analysis, rule chất lượng, coverage | Tìm lỗi tiềm ẩn và đánh giá bằng chứng test. | Vừa |
| 5 | Dependency, license, SAST hoặc kiểm tra bảo mật theo cấu hình | Phát hiện rủi ro thư viện và mẫu code nguy hiểm. | Thấp đến cao, tùy công cụ |
| 6 | Component, integration, contract test | Kiểm chứng tương tác giữa các thành phần. | Vừa đến cao |
| 7 | Deploy preview, smoke và end-to-end | Kiểm chứng luồng qua môi trường gần thực tế. | Cao |
| 8 | Performance, load, resilience, kiểm thử chuyên sâu | Đánh giá tải, độ trễ, phục hồi và giới hạn tài nguyên. | Cao |
| 9 | Review chuyên môn, release approval theo rủi ro | Xác nhận các quyết định cần hiểu bối cảnh và thẩm quyền. | Phụ thuộc thay đổi |

**Bảo mật không nên bị đẩy hết xuống cuối pipeline.** Một secret scan nhanh có thể chạy rất sớm; phân tích dependency và SAST có thể chạy song song với test; kiểm thử DAST hoặc kiểm tra trong môi trường triển khai có thể tốn kém hơn. Thứ tự cần dựa trên **chi phí, khả năng phát hiện, mức rủi ro và quan hệ phụ thuộc**, không chỉ tên loại kiểm tra.

## 4. Tầng 1: kiểm tra nhanh trước khi biên dịch

Những lỗi cơ học thường dễ phát hiện và sửa:

- Formatter check phát hiện mã không theo cấu hình.
- Kiểm tra whitespace phát hiện một số lỗi trình bày.
- Kiểm tra cú pháp YAML/JSON/TOML và cấu hình build.
- Kiểm tra secret đã biết hoặc khóa riêng bị đưa vào source.
- Kiểm tra file sinh tự động có bị sửa tay trái quy trình không.
- Kiểm tra tên file, cấu trúc package hoặc quy tắc repository có thể xác minh nhanh.

Các kiểm tra này phù hợp chạy ở local trước khi push và chạy lại trong CI để tạo **kết quả nhất quán**.

### Ví dụ: formatter check

~~~bash
# Lệnh minh họa; dùng đúng task/công cụ được cấu hình trong dự án.
./gradlew spotlessCheck
~~~

Nếu dự án không dùng Spotless hoặc Gradle, lệnh này không áp dụng. Ý nghĩa của bước là **kiểm tra**, không tự ý format toàn repository trong CI rồi âm thầm sửa source của pull request.

CI nên trả kết quả như:

- File nào không đạt?
- Rule nào bị vi phạm?
- Có lệnh chuẩn nào để tác giả chạy lại?
- Đây là lỗi bắt buộc hay cảnh báo?

Đừng chỉ trả “quality gate failed” mà không có đường dẫn tới nguyên nhân.

### Secret scan cần được đưa sớm

Nếu source chứa API key hoặc private key, lỗi có thể gây hậu quả ngay khi commit được đẩy lên remote. Vì vậy, secret scanning thường nên chạy ở pre-commit hoặc đầu pipeline, và vẫn có kiểm tra ở phía server để không phụ thuộc hoàn toàn vào máy cá nhân.

Nếu phát hiện secret đã bị lộ, **xóa dòng khỏi commit mới không tự thu hồi secret**. Cần quy trình thu hồi/rotate và xử lý lịch sử theo chính sách bảo mật.

## 5. Tầng 2: compile và kiểm tra cấu hình

Sau các kiểm tra nhanh, bước compile giúp phát hiện:

- Lỗi cú pháp.
- Thiếu class hoặc method.
- Kiểu dữ liệu không tương thích.
- Import hoặc dependency không hợp lệ.
- Sai cấu hình annotation processor hoặc generated source.
- Một số vấn đề schema/build có thể xác minh ở thời điểm biên dịch.

Compile thường rẻ hơn một bộ integration/end-to-end đầy đủ, nhưng vẫn cần thời gian resolve dependency, chạy compiler và sinh mã.

**Compile thành công không chứng minh logic đúng.** Một điều kiện dùng > thay cho >= vẫn biên dịch bình thường; một truy vấn hợp lệ về cú pháp vẫn có thể đọc sai dữ liệu.

### Không chạy kiểm tra sâu trên source không build được nếu nó phụ thuộc artifact

Một số công cụ static analysis cần bytecode hoặc classpath đầy đủ. Nếu compile thất bại, việc cố chạy phân tích phụ thuộc vào kết quả compile có thể tạo hàng loạt lỗi giả hoặc kết quả không đáng tin.

Vì vậy, hãy phân biệt:

- Kiểm tra **độc lập với compile** có thể chạy sớm hoặc song song.
- Kiểm tra **cần output của compile** phải chờ compile hoàn tất.
- Khi compile lỗi, pipeline nên báo nguyên nhân gốc thay vì tạo một danh sách nhiễu từ các bước downstream.

## 6. Tầng 3: unit test cho logic có thể cô lập

Unit test thường có thời gian chạy ngắn hơn integration/e2e và cho kết quả gần với logic đang thay đổi. Đây là nơi phù hợp để kiểm tra:

- Giá trị biên.
- Tiền điều kiện và dữ liệu không hợp lệ.
- Nhánh quyết định.
- Ngoại lệ được cam kết.
- Bất biến của hàm hoặc đối tượng.
- Tác dụng phụ qua ranh giới giả lập khi tác dụng phụ là một phần hợp đồng.

Ví dụ Java 17:

~~~java
public final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;

    private ShippingFeePolicy() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }

        long standardFee = subtotalVnd >= FREE_THRESHOLD
                ? 0L
                : STANDARD_FEE;

        return standardFee + (express ? EXPRESS_SURCHARGE : 0L);
    }
}
~~~

Unit test JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeePolicyTest {
    @ParameterizedTest
    @CsvSource({
            "0, false, 30000",
            "499999, false, 30000",
            "500000, false, 0",
            "500001, false, 0",
            "500000, true, 20000"
    })
    void calculatesExpectedFee(
            long subtotal, boolean express, long expected) {
        assertEquals(expected,
                ShippingFeePolicy.calculate(subtotal, express));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.calculate(-1L, false));
    }
}
~~~

Các expected value được suy từ hợp đồng giả định. Unit test này có thể bắt lỗi ở đúng ngưỡng nhanh hơn một luồng đặt hàng end-to-end.

Tuy nhiên, unit test không chứng minh controller đã gọi đúng policy, transaction được commit đúng hoặc JSON response tương thích. Những điều đó cần kiểm tra ở ranh giới tương ứng.

## 7. Tầng 4: static analysis và coverage gate

Static analysis có thể phát hiện các vấn đề mà compile không báo:

- Null dereference tiềm ẩn.
- Tài nguyên không được đóng.
- Nhánh điều kiện đáng ngờ.
- API nguy hiểm hoặc cách xử lý dữ liệu thiếu an toàn.
- Code không dùng, duplicate hoặc cấu trúc phức tạp theo rule.
- Vi phạm quy ước kiến trúc hoặc dependency.

Coverage gate cung cấp tín hiệu về mức test chạy qua dòng hoặc nhánh, nhưng **coverage cao không đồng nghĩa test có oracle tốt**. Một test có thể đi qua nhánh mà không kiểm tra kết quả đúng.

### Gate coverage nên gắn với thay đổi và phạm vi

Một số lựa chọn:

- Đặt ngưỡng cho toàn bộ module khi baseline đã đủ ổn định.
- Đo coverage của code mới/thay đổi để tránh làm ngưỡng hiện tại bất khả thi ngay lập tức.
- Đặt yêu cầu riêng cho vùng rủi ro cao như phân quyền, thanh toán hoặc migration.
- Theo dõi xu hướng thay vì chặn chỉ vì một thay đổi nhỏ làm tỷ lệ toàn dự án dao động.

Nếu một dự án có 10.000 dòng cũ với coverage thấp, thêm một phương thức nhỏ có test tốt có thể làm tỷ lệ tổng gần như không đổi. Ngược lại, chỉ thêm test cho getter có thể tăng coverage nhưng không tăng nhiều bằng chứng về hành vi quan trọng.

### Static analysis có thể chạy song song không?

Nếu công cụ chỉ cần source và cấu hình, nó có thể chạy song song với compile hoặc unit test. Nếu nó cần bytecode, test report hay classpath đã build, phải chờ các artifact đó. Thiết kế pipeline theo **dependency thật của từng công cụ**, không buộc mọi thứ vào một chuỗi tuần tự duy nhất.

## 8. Tầng 5: dependency, license và kiểm tra bảo mật

Những kiểm tra này có chi phí khác nhau và nên phân tầng:

| Kiểm tra | Có thể chạy sớm khi nào? | Điều cần lưu ý |
| --- | --- | --- |
| Secret scan | Ngay trên diff hoặc source checkout. | Secret đã lộ cần thu hồi, không chỉ xóa khỏi file. |
| Dependency inventory/SCA | Sau khi đọc manifest/lockfile hoặc resolve dependency. | Kết quả phụ thuộc database lỗ hổng và phiên bản advisory. |
| License policy | Khi dependency graph đã xác định. | Quy tắc chấp nhận license thuộc chính sách tổ chức. |
| SAST | Có thể chạy trên source; một số tool cần compile database/bytecode. | Phải phân loại severity, confidence và false positive. |
| Container/image scan | Sau khi build image. | Chờ artifact; vẫn cần kiểm tra image thực sự phát hành. |
| DAST | Khi có ứng dụng chạy trong môi trường thử nghiệm. | Thường tốn kém hơn và phụ thuộc môi trường/seed data. |

Không nên dùng một gate duy nhất “security passed” mà không nói đã kiểm tra gì. Cần phân biệt **không có phát hiện**, **không chạy**, **bị bỏ qua do lỗi công cụ** và **có ngoại lệ được chấp nhận**.

### Mức độ nghiêm trọng và mức độ chắc chắn

Một phát hiện SAST có severity cao nhưng confidence thấp cần được điều tra nhanh; không nên tự động bỏ qua chỉ vì có thể false positive. Một dependency có CVE nhưng không nằm trên đường code sử dụng vẫn cần đánh giá theo exploitability, khả năng tiếp cận, phiên bản và chính sách tổ chức.

Các ngoại lệ cần có:

- Người chịu trách nhiệm phê duyệt.
- Lý do và bằng chứng.
- Phạm vi phiên bản/đường sử dụng.
- Thời hạn xem lại nếu ngoại lệ tạm thời.
- Biện pháp giảm thiểu khi chưa thể nâng cấp.

**Không được biến việc tạm chấp nhận rủi ro thành trạng thái vĩnh viễn không owner.**

## 9. Tầng 6: component, integration và contract tests

Khi logic cần tương tác với database, message broker, filesystem hoặc API ngoài, unit test không đủ để xác minh mọi hợp đồng.

- **Component test:** kiểm tra một thành phần cùng các phụ thuộc được kiểm soát.
- **Integration test:** kiểm tra tương tác kỹ thuật thật giữa các thành phần.
- **Contract test:** kiểm tra provider và consumer tuân theo schema, endpoint, message hoặc quy tắc đã thỏa thuận.

Các test này thường chậm hơn unit test do khởi tạo môi trường, container, dữ liệu và kết nối.

Ví dụ những lỗi chỉ integration test dễ phát hiện:

- Transaction không rollback khi bước ghi thứ hai thất bại.
- Mapping JSON làm mất field hoặc đổi kiểu.
- Cấu hình DI không tạo đúng implementation.
- Migration không chạy được trên phiên bản database mục tiêu.
- Consumer xác nhận message trước khi xử lý bền vững.
- Client và provider không còn tương thích.

**Chậm hơn không có nghĩa ít quan trọng hơn.** Nếu PR thay đổi transaction, schema hoặc message contract, các test tương ứng có thể là điều kiện merge bắt buộc.

### Tối ưu bằng phạm vi liên quan

Có thể chạy integration test theo module hoặc service bị ảnh hưởng, nếu dependency graph và quy tắc chọn test đủ tin cậy. Nhưng không nên chỉ dựa vào tên file để bỏ qua test: một thay đổi ở shared library có thể ảnh hưởng nhiều consumer.

## 10. Tầng 7: end-to-end và smoke test

End-to-end test đi qua nhiều lớp thật hơn, ví dụ:

~~~text
Browser / API client
  -> HTTP endpoint
  -> application service
  -> database
  -> message/event
  -> downstream consumer
  -> response hoặc trạng thái người dùng nhìn thấy
~~~

Chúng hữu ích để kiểm chứng một số luồng quan trọng từ góc nhìn người dùng, nhưng thường:

- Chậm hơn và cần môi trường triển khai.
- Nhạy với dữ liệu, thời gian và thứ tự thực thi.
- Khó xác định nguyên nhân nếu thất bại ở một trong nhiều thành phần.
- Có thể flaky nếu test dùng chung state hoặc phụ thuộc dịch vụ ngoài.

Vì vậy, không nên biến mọi nhánh logic thành một E2E test. Dùng E2E cho **luồng tích hợp quan trọng**, còn chi tiết quyết định và dữ liệu biên nên được bảo vệ gần tầng logic hơn.

**Smoke test** thường kiểm tra nhanh ứng dụng đã triển khai có khởi động và thực hiện được một số thao tác cốt lõi không. Smoke test không thay thế regression suite.

## 11. Tầng 8: performance, load và resilience test

Kiểm thử hiệu năng thường tốn kém vì cần môi trường và workload đại diện. Nó có thể kiểm tra:

- Latency p50/p95/p99.
- Throughput và error rate ở tải mục tiêu.
- Queue depth, số tác vụ đồng thời và connection pool.
- Memory, allocation, thời gian GC.
- Hành vi khi phụ thuộc chậm, mất kết nối hoặc trả lỗi.
- Khả năng phục hồi sau burst hoặc restart.

Không phải mọi PR đều cần chạy load test đầy đủ. Có thể dùng:

- Benchmark nhỏ cho thay đổi thuật toán nhạy hiệu năng.
- Test hiệu năng theo component khi một hotspot bị thay đổi.
- Load test ở pre-release hoặc theo lịch định kỳ.
- Resilience test cho thay đổi timeout, retry, circuit breaker và queue.
- So sánh với baseline trên môi trường kiểm soát.

Nhưng nếu PR thay đổi **pool kết nối, thuật toán xử lý tải, giới hạn queue hoặc đường gọi phụ thuộc**, việc trì hoãn mọi kiểm tra hiệu năng đến sau release có thể tạo rủi ro không chấp nhận được.

### Tránh so sánh benchmark không cùng điều kiện

Một kết quả “nhanh hơn 20%” không đáng tin nếu chạy trên máy khác, dữ liệu khác, JVM warm-up khác hoặc số request khác. Cần ghi rõ:

- Phiên bản build và cấu hình JVM.
- Hardware/runner và môi trường.
- Kích thước, phân phối dữ liệu.
- Số lần warm-up và số lần đo.
- Metric được so sánh và sai số/biến thiên.

Gate hiệu năng nên dựa trên **ngân sách và phương pháp đã thống nhất**, không phải một con số benchmark đơn lẻ.

## 12. Review con người không nhất thiết phải đợi mọi test kết thúc

Một quy trình dễ hiểu có thể khiến reviewer chỉ bắt đầu đọc sau khi tất cả CI hoàn tất. Nhưng điều đó có thể kéo dài tổng thời gian chờ không cần thiết.

Có thể diễn ra song song:

- Tác giả đẩy PR và CI chạy các gate tự động.
- Reviewer xem mục tiêu, diff và thiết kế trong khi các bước độc lập đang chạy.
- Kết quả test nhanh xuất hiện để định hướng câu hỏi.
- Khi test tích hợp hoàn tất, reviewer xác nhận các vùng phụ thuộc.
- Chỉ merge khi **mọi điều kiện bắt buộc** đạt và các quyết định còn mở được giải quyết.

Review sớm không có nghĩa duyệt khi chưa có bằng chứng. Nó giúp tận dụng thời gian CI, nhưng reviewer vẫn cần xem kết quả cuối cùng và diff mới nhất trước khi approve.

Nếu tác giả push commit mới sau khi reviewer đã xem, cần biết **approval có còn hợp lệ** theo chính sách repository hay không.

## 13. Chạy song song những kiểm tra độc lập

Nguyên tắc “nhanh trước, chậm sau” giúp phát hiện lỗi sớm, nhưng tuần tự hóa toàn bộ pipeline có thể làm tăng thời gian tổng.

Ví dụ:

~~~mermaid
flowchart TD
    A["Checkout + resolve source"] --> B["Format / whitespace"]
    A --> C["Secret scan"]
    A --> D["Validate configuration"]
    B --> E["Compile"]
    D --> E
    E --> F["Unit tests"]
    E --> G["Static analysis cần bytecode"]
    A --> H["Dependency scan từ manifest"]
    F --> I["Integration tests"]
    G --> I
    H --> I
    I --> J["Deploy preview"]
    J --> K["Smoke / E2E"]
    K --> L["Performance hoặc release suite theo rủi ro"]
~~~

Trong sơ đồ:

- **Format, secret scan và config validation** có thể độc lập nếu chúng không cần output của nhau.
- **Compile** phải hoàn tất trước những kiểm tra cần bytecode.
- **Unit test** và static analysis có thể chạy song song sau compile nếu tài nguyên cho phép.
- **Dependency scan** có thể chạy từ manifest/lockfile song song với compile; một số bước kiểm tra sâu hơn có thể cần image hoặc artifact.
- **Integration/E2E** phải chờ ứng dụng và phụ thuộc thử nghiệm sẵn sàng.

Đây là ví dụ dependency graph. Pipeline thực tế cần tránh các job cùng tranh chấp một database hoặc môi trường test dùng chung.

### Parallelism có chi phí

Chạy mọi thứ đồng thời có thể:

- Tăng nhu cầu CPU/RAM và làm tất cả job chậm hơn.
- Làm database test quá tải.
- Tạo tranh chấp cổng, file, container và dữ liệu.
- Khiến log nhiều hơn và khó đọc.
- Làm chi phí CI tăng dù thời gian chờ của một PR không giảm đáng kể.

Mục tiêu là **tối ưu thời gian phản hồi thực tế và chi phí tài nguyên**, không tối đa số job chạy đồng thời.

## 14. Fail-fast đúng cách: dừng bước phụ thuộc, vẫn giữ thông tin hữu ích

Giả sử compile thất bại. Các bước cần bytecode không nên tiếp tục và tạo hàng trăm lỗi kiểu “class not found”. Nhưng secret scan hoặc kiểm tra manifest độc lập vẫn có thể hoàn tất.

Một chính sách phù hợp:

1. Dừng hoặc skip các job **phụ thuộc vào artifact đã thất bại**.
2. Giữ kết quả từ các job **độc lập đã chạy**.
3. Báo lỗi gốc ở đầu kết quả.
4. Không biến job bị skip thành job thành công.
5. Hiển thị rõ trạng thái **failed, skipped, cancelled, not run**.

Tương tự, nếu unit test thất bại, có thể không cần chạy full E2E cho mọi PR. Nhưng với thay đổi rủi ro cao, nhóm có thể muốn vẫn thu thập một số kết quả độc lập để chẩn đoán. Quyết định đó cần cân bằng giữa chi phí và giá trị thông tin.

**Fail-fast không có nghĩa che giấu các lỗi độc lập**, cũng không có nghĩa dùng trạng thái “green” cho bước chưa chạy.

## 15. Phân biệt điều kiện chặn và tín hiệu cảnh báo

Một quality gate cần có chính sách rõ:

| Kết quả | Cách xử lý thường phù hợp |
| --- | --- |
| Compile thất bại | Blocking: không thể tích hợp mã chưa biên dịch được. |
| Unit test bắt buộc thất bại | Blocking: cần sửa hoặc giải thích baseline/flake theo quy trình. |
| Formatter check thất bại | Blocking nếu repository đã thống nhất formatter check là điều kiện merge. |
| Secret xác nhận bị lộ | Blocking và cần quy trình thu hồi/rotate. |
| Lỗ hổng nghiêm trọng có thể khai thác | Blocking hoặc cần phê duyệt rủi ro đúng thẩm quyền trước khi tiếp tục. |
| Static analysis cảnh báo thấp, đã được đánh giá | Có thể advisory hoặc xử lý theo backlog. |
| Coverage giảm nhẹ ở vùng không trọng yếu | Có thể cảnh báo; nhưng nếu vi phạm ngưỡng đã chốt thì theo policy. |
| Benchmark dao động trong giới hạn nhiễu | Cần đo lại/quan sát, không kết luận vội. |
| E2E test flaky đã xác định | Không nên tự động coi là pass; cần owner và chính sách xử lý rõ. |

Bảng là hướng dẫn, không thay thế chính sách bảo mật, tuân thủ hoặc phát hành của tổ chức. Một finding có thể cần **chặn dù phát hiện ở bước tốn kém**, vì hậu quả quá lớn.

Không nên tạo cơ chế override tùy tiện. Nếu cho phép bỏ qua gate, cần:

- Người phê duyệt phù hợp.
- Lý do và bằng chứng.
- Phạm vi và thời hạn ngoại lệ.
- Biện pháp giảm thiểu.
- Theo dõi đến khi đóng ngoại lệ.

## 16. Flaky test và chất lượng của chính pipeline

Một test đôi lúc pass, đôi lúc fail trên cùng commit là **flaky test**. Nếu không xử lý, pipeline có thể làm người phát triển mất thời gian rerun và giảm niềm tin vào gate.

Nguyên nhân thường gặp:

- Phụ thuộc thời gian thực hoặc timezone.
- Chia sẻ trạng thái giữa test.
- Thứ tự thực thi không được kiểm soát.
- Dùng network/dịch vụ bên ngoài không ổn định.
- Race condition hoặc timeout quá chặt.
- Seed ngẫu nhiên không được ghi lại.
- Dọn dẹp tài nguyên không đầy đủ.

Cách xử lý:

1. Ghi nhận test, commit, environment và log.
2. Tìm điều kiện gây không ổn định, không chỉ rerun đến khi xanh.
3. Cô lập dữ liệu và clock khi phù hợp.
4. Dùng retry có giới hạn **như biện pháp chẩn đoán hoặc giảm gián đoạn tạm thời**, không coi retry là sửa nguyên nhân.
5. Có owner và thời hạn xử lý test flaky.
6. Không âm thầm biến test quan trọng thành advisory vô thời hạn.

Nếu một test bị đánh dấu quarantine, phải thể hiện rõ **test không chạy trong gate hiện tại**, rủi ro còn lại và nơi theo dõi.

## 17. Tối ưu pipeline theo thời gian phản hồi, không chỉ thời lượng tổng

Hai pipeline có thể có tổng thời gian 20 phút nhưng trải nghiệm khác nhau:

- Pipeline A: 15 phút không có kết quả, cuối cùng báo formatter fail.
- Pipeline B: sau 10 giây báo formatter pass; sau 1 phút compile pass; sau 3 phút unit test fail.

Pipeline B cho phản hồi hữu ích sớm hơn dù full run vẫn cần thời gian.

Các chỉ số vận hành pipeline nên quan sát:

| Metric | Câu hỏi |
| --- | --- |
| **Time to first actionable feedback** | Bao lâu sau khi push, tác giả nhận được lỗi có thể xử lý đầu tiên? |
| **Time to required green** | Bao lâu để mọi gate bắt buộc hoàn tất? |
| **Queue/wait time** | Job mất bao lâu chờ runner hoặc môi trường? |
| **Execution time by stage** | Bước nào thực sự tốn thời gian? |
| **Failure rate by stage** | Gate nào hay thất bại và vì nguyên nhân gì? |
| **Flaky rate** | Bao nhiêu lần thất bại không tái hiện ổn định? |
| **Rerun rate** | Nhóm có thường phải chạy lại do môi trường hoặc test không? |
| **Cost per PR/build** | Tài nguyên CI được dùng bao nhiêu? |
| **False-positive/override rate** | Bao nhiêu cảnh báo bị xác nhận không phù hợp hoặc phải bỏ qua? |

**Không tối ưu một metric đơn lẻ.** Giảm time-to-first-feedback bằng cách bỏ unit test bắt buộc có thể làm trải nghiệm nhanh hơn nhưng tăng rủi ro. Tăng số job song song có thể giảm wall-clock nhưng đội chi phí và flaky.

## 18. Phạm vi gate nên phụ thuộc loại thay đổi

Không phải PR nào cũng cần cùng một chuỗi kiểm tra đầy đủ. Tuy vậy, cần tránh dùng nhãn “chỉ là thay đổi nhỏ” để bỏ qua rủi ro.

| Loại thay đổi | Kiểm tra thường cần ưu tiên | Có thể bổ sung theo rủi ro |
| --- | --- | --- |
| **Format-only** | Formatter check, diff review, compile/test liên quan nếu phạm vi rộng. | Test tương đương hoặc kiểm tra đặc biệt với literal/config nhạy whitespace. |
| **Logic nghiệp vụ** | Compile, unit test với biên và lỗi, static analysis. | Integration/contract/e2e nếu chạm caller hoặc dữ liệu thật. |
| **API/schema** | Compile, contract/schema compatibility, unit test. | Integration với consumer, migration và rollout. |
| **Database migration** | Validate migration, unit/component test. | Test trên phiên bản DB mục tiêu, backup/rollback và dữ liệu đại diện. |
| **Authentication/authorization** | Static/security checks, unit test đường permit/deny/error. | Integration/e2e với principal, tenant và policy thật. |
| **Dependency upgrade** | Compile, unit test, license/SCA. | Integration, compatibility và performance khi dependency ảnh hưởng runtime. |
| **Queue/concurrency/pool** | Unit test, static analysis và giới hạn cấu hình. | Load, stress, resilience và quan sát dependency. |
| **Thay đổi UI đơn giản** | Lint, compile, unit/component test. | E2E cho luồng người dùng quan trọng. |

Có thể dùng path-based hoặc label-based workflow để chọn thêm test liên quan, nhưng điều kiện chọn phải đủ tin cậy. Nếu một thay đổi shared library có nhiều consumer, không được bỏ integration test chỉ vì PR không sửa trực tiếp file của consumer.

## 19. Ví dụ pipeline khai báo theo giai đoạn

Đoạn YAML dưới đây là **mô hình minh họa**, không phải cấu hình CI hoàn chỉnh cho một nhà cung cấp cụ thể:

~~~yaml
stages:
  - quick_checks
  - compile
  - unit_tests
  - static_and_security
  - integration
  - end_to_end
  - performance

quick_checks:
  checks:
    - formatter_check
    - whitespace_check
    - config_validation
    - secret_scan

compile:
  needs:
    - quick_checks
  checks:
    - compile_production
    - compile_tests

unit_tests:
  needs:
    - compile
  checks:
    - unit_tests_fast

static_and_security:
  needs:
    - compile
  parallel:
    - static_analysis
    - dependency_scan
    - license_policy

integration:
  needs:
    - unit_tests
    - static_and_security
  checks:
    - component_tests
    - integration_tests
    - contract_tests

end_to_end:
  needs:
    - integration
  checks:
    - deploy_preview
    - smoke_tests
    - critical_user_flows

performance:
  needs:
    - compile
  policy:
    run_on:
      - performance_sensitive_changes
      - release_candidate
      - scheduled_baseline
~~~

Một số điểm quan trọng:

- Trường needs mô tả dependency; nó không phải cú pháp YAML chuẩn của mọi CI provider.
- Static analysis và dependency scan được minh họa chạy song song sau compile, nhưng dependency scan chỉ cần manifest có thể chạy sớm hơn.
- Performance test được chọn theo thay đổi nhạy hiệu năng hoặc release candidate; nếu sản phẩm yêu cầu performance gate cho mọi PR, policy phải thể hiện điều đó.
- Một job bị skip do điều kiện phải được báo là **skipped**, không tự động coi là passed.
- Các stage blocking cần được khai báo rõ trong branch protection/merge policy của nền tảng.

## 20. Khi nào nên chạy full suite?

Full suite có thể bao gồm tất cả unit, integration, contract, E2E, migration, security và performance test. Nó tốn kém hơn nhưng hữu ích ở các mốc:

- Trước release candidate.
- Trước phát hành có rủi ro cao.
- Sau thay đổi shared library hoặc nền tảng dùng chung.
- Theo lịch để phát hiện regression ngoài phạm vi PR gần nhất.
- Khi thay đổi dependency hoặc runtime có ảnh hưởng rộng.
- Khi pipeline chọn test theo phạm vi không thể bảo đảm bao phủ đầy đủ.

Không phải lúc nào cũng cần chạy full suite trước mọi commit, nhưng release không nên dựa hoàn toàn vào tập test rút gọn nếu chính sách yêu cầu bằng chứng đầy đủ.

Một cách kết hợp:

- **Local/PR:** feedback nhanh và test liên quan.
- **Merge queue/main:** kiểm tra tích hợp rộng hơn trên trạng thái commit thực sự sẽ được merge.
- **Pre-release:** full regression, security và performance theo mức rủi ro.
- **Scheduled:** quét sâu, test dài và đo xu hướng.

Lưu ý: nếu có commit mới được đưa vào merge queue sau khi PR đã xanh, phải chạy lại các gate cần thiết trên **tổ hợp mã cuối cùng**, tránh kết luận từ trạng thái cũ.

## 21. Những anti-pattern trong sắp xếp quality gate

| Anti-pattern | Hệ quả | Hướng cải thiện |
| --- | --- | --- |
| **E2E chạy trước formatter/compile** | Tốn thời gian để phát hiện lỗi cơ bản. | Đưa kiểm tra rẻ và độc lập lên sớm. |
| **Mọi job chạy tuần tự** | Wall-clock dài dù nhiều bước độc lập. | Mô hình hóa dependency và chạy song song có giới hạn. |
| **Mọi job chạy song song không kiểm soát** | Runner, DB và môi trường bị tranh chấp. | Đặt concurrency limit và nhóm job theo tài nguyên. |
| **Security chỉ chạy sau release** | Rủi ro có thể đến quá muộn. | Secret/SAST/SCA phù hợp chạy sớm; DAST chạy khi có môi trường. |
| **Unit test bị bỏ qua vì integration đã xanh** | Mất phản hồi nhanh cho logic nhỏ và test biên. | Giữ unit test gần logic; dùng integration cho tương tác. |
| **Gate thất bại không có chi tiết** | Tác giả không biết sửa ở đâu. | Trả file, rule, log và hướng xử lý. |
| **Flaky test được rerun đến khi pass** | Lỗi không ổn định bị che khuất. | Theo dõi flaky, tìm nguyên nhân và quản lý quarantine. |
| **Job bị skip nhưng báo xanh** | Tạo cảm giác đã kiểm chứng dù thực tế chưa chạy. | Phân biệt pass, fail, skipped và not run. |
| **Mọi cảnh báo đều blocking** | Review chậm, nhóm bỏ qua hoặc tìm cách vô hiệu hóa gate. | Phân loại severity, confidence và owner. |
| **Override không thời hạn** | Ngoại lệ trở thành quy tắc ngầm. | Ghi lý do, owner, hạn xem lại và biện pháp giảm thiểu. |
| **Chỉ chạy test theo file diff** | Bỏ sót caller/consumer bị ảnh hưởng gián tiếp. | Dùng dependency graph, contract và vùng tác động. |

## 22. Quy trình xử lý khi một gate thất bại

Khi CI báo đỏ, đừng bắt đầu bằng việc chạy lại toàn bộ pipeline nhiều lần. Hãy xác định **job nào thất bại, job nào bị skip và job nào có thể đã bị ảnh hưởng dây chuyền**.

1. **Xác định revision:** Kết quả thuộc commit nào? Có commit mới sau đó không?
2. **Tìm lỗi gốc:** Job nào phát hiện vấn đề đầu tiên? Có phải lỗi downstream do artifact thiếu?
3. **Phân loại:** lỗi code, test, môi trường, flaky, dữ liệu hoặc cấu hình?
4. **Đánh giá phạm vi:** Chỉ một module hay nhiều job dùng chung phụ thuộc?
5. **Chọn bước chạy lại nhỏ nhất:** rerun test liên quan sau khi xác minh môi trường; không rerun toàn bộ chỉ theo thói quen.
6. **Sửa hoặc ghi ngoại lệ:** có bằng chứng và owner nếu chấp nhận rủi ro.
7. **Xác minh trạng thái cuối:** tất cả gate bắt buộc đã chạy trên đúng revision được merge/phát hành chưa?

Một ví dụ:

~~~text
formatter_check: FAILED
compile: SKIPPED (depends on quick_checks)
secret_scan: PASSED
unit_tests: NOT RUN
integration_tests: NOT RUN
~~~

Ở đây, không thể kết luận “CI có 1 lỗi và các test còn lại xanh”. Thực tế chỉ biết formatter fail, secret scan pass, compile bị skip và test chưa chạy.

**Trạng thái chưa chạy không phải trạng thái thành công.**

## 23. Thiết kế thông báo lỗi giúp tác giả hành động nhanh

Một quality gate tốt không chỉ phát hiện mà còn giúp người sửa biết **bước tiếp theo**.

Thông báo hữu ích thường có:

- **Tên job và rule** đã thất bại.
- **File/dòng hoặc artifact** liên quan.
- **Thông điệp ngắn giải thích** điều kiện không đạt.
- **Lệnh hoặc hướng dẫn tái hiện** nếu có.
- **Link log/report** đầy đủ.
- **Owner hoặc kênh hỗ trợ** cho lỗi môi trường/policy.
- **Trạng thái phụ thuộc:** các bước nào bị skip vì job này.

Tránh:

~~~text
Quality gate failed.
Please fix and retry.
~~~

Tốt hơn:

~~~text
Job: unit_tests_fast
Failed test: ShippingFeePolicyTest.atThresholdIsFree
Expected: 0
Actual: 30000
Revision: abc123
Next step: kiểm tra điều kiện tại ngưỡng 500_000 VND.
Log: xem report test của job.
~~~

Ví dụ thông báo thứ hai giúp tác giả xác định ngay **đầu vào, expected, actual và vùng cần xem**. Không đưa secret, dữ liệu cá nhân hoặc payload nhạy cảm vào log công khai.

## 24. Cổng chất lượng không thay thế trách nhiệm review

Một pipeline có thể xanh mà vẫn tồn tại:

- Yêu cầu nghiệp vụ bị hiểu sai nhưng test được viết theo cùng giả định sai.
- Test chỉ kiểm tra happy path.
- API đổi theo cách phá client cũ nhưng không có contract test cho consumer.
- Một lỗ hổng nằm ngoài rule hoặc phiên bản scanner hiện tại.
- Một quyết định kiến trúc làm tăng chi phí thay đổi nhưng chưa vi phạm rule tự động.
- Tài liệu vận hành vẫn sai dù source và test đều đúng.

Ngược lại, một cảnh báo tự động có thể là false positive hoặc chưa phản ánh bối cảnh. Người có thẩm quyền vẫn cần đánh giá.

**Quality gate cung cấp bằng chứng có giới hạn; reviewer và owner chịu trách nhiệm hiểu bối cảnh và quyết định rủi ro.**

Không nên đặt mục tiêu “pipeline xanh bằng mọi giá”. Mục tiêu là **thay đổi đạt tiêu chí chất lượng đã thống nhất**, và nếu có ngoại lệ thì ngoại lệ được nhìn thấy, có lý do và có người chịu trách nhiệm.

## 25. Checklist thiết kế thứ tự gate

Trước khi thêm hoặc sắp xếp lại pipeline, hãy hỏi:

1. **Kiểm tra nào phát hiện lỗi phổ biến nhanh nhất?** Có thể chạy trước compile không?
2. **Job nào phụ thuộc output của job khác?** Có dependency thật hay chỉ đang xếp tuần tự theo thói quen?
3. **Những job độc lập nào có thể chạy song song?** Chúng có tranh chấp runner, DB hoặc môi trường không?
4. **Kiểm tra bảo mật nhanh nào cần chạy sớm?** Secret, SAST/SCA phù hợp?
5. **Unit test nào có thể thay feedback chậm bằng test nhỏ hơn?** Có giữ đủ bằng chứng không?
6. **Gate nào phải blocking theo rủi ro và policy?** Có tiêu chí severity/confidence rõ không?
7. **Gate nào chỉ advisory?** Có owner và cách xử lý cảnh báo không?
8. **Job bị skip được biểu diễn thế nào?** Có ai hiểu nhầm skip thành pass không?
9. **Flaky test được theo dõi và xử lý ra sao?** Có retry vô hạn hoặc quarantine vô chủ không?
10. **Có chạy lại trên revision cuối cùng không?** Merge queue hoặc commit mới có làm kết quả cũ mất hiệu lực không?
11. **Thông báo thất bại có hành động cụ thể không?** Tác giả có biết sửa ở đâu?
12. **Pipeline có đo thời gian phản hồi và chi phí không?** Thay đổi thứ tự có thực sự cải thiện trải nghiệm?

## 26. Bài tập tự luyện

### Tình huống A — Integration test trước compile

Một pipeline khởi tạo database container, deploy ứng dụng và chạy E2E trong 18 phút. Sau đó formatter check mới báo sai một dòng import.

**Câu hỏi:** Nên thay đổi thứ tự thế nào?

**Gợi ý:** Chạy formatter/whitespace/config và compile trước. Sau đó unit test, static/security độc lập theo dependency; chỉ triển khai môi trường tích hợp khi các điều kiện cần thiết đã đạt.

### Tình huống B — Secret scan chạy cuối

Một nhóm chỉ chạy secret scan sau khi deploy staging vì scanner được cấu hình chung trong job security dài 30 phút.

**Câu hỏi:** Có cách nào giảm thời gian phát hiện mà không bỏ kiểm tra sâu?

**Gợi ý:** Tách secret scan nhanh chạy trên diff/source ngay đầu pipeline; giữ các kiểm tra bảo mật cần build artifact hoặc môi trường ở bước phù hợp. Secret đã lộ vẫn cần rotate/revoke.

### Tình huống C — Mọi test chạy song song

Sau khi chuyển toàn bộ integration test sang chạy đồng thời, database dùng chung bị quá tải và tỷ lệ flaky tăng.

**Câu hỏi:** Vì sao “chạy song song nhiều hơn” không làm pipeline tốt hơn?

**Gợi ý:** Các job tranh chấp tài nguyên. Cần giới hạn concurrency, cô lập database/schema hoặc chia nhóm tài nguyên, đo thời gian thực và flaky rate.

### Tình huống D — Job bị skip vẫn xanh

Compile fail nên integration test bị skip, nhưng giao diện CI hiển thị một dấu xanh chung cho toàn stage.

**Câu hỏi:** Nguy cơ là gì?

**Gợi ý:** Người xem tưởng integration đã chạy và pass. Cần hiển thị rõ failed/skipped/not run và chỉ đánh giá gate theo policy minh bạch.

### Tình huống E — Coverage gate làm nhóm viết test hình thức

Nhóm đặt ngưỡng line coverage 90%. Developer thêm test gọi getter và setter để tăng phần trăm nhưng không kiểm tra kết quả nghiệp vụ.

**Câu hỏi:** Gate đang tối ưu điều gì và còn thiếu gì?

**Gợi ý:** Coverage đo code được thực thi, không chứng minh expected đúng. Cần tập trung test oracle, nhánh quan trọng, lỗi và tác dụng phụ; xem coverage như tín hiệu chứ không là mục tiêu duy nhất.

### Tình huống F — PR sửa connection pool

Một PR đổi maximum pool size và queue timeout. Unit test vẫn xanh, nhưng integration test hiện không tạo tải và performance test chỉ chạy hàng tháng.

**Câu hỏi:** Nên thêm kiểm tra nào trước khi phát hành?

**Gợi ý:** Kiểm thử tải và resilience đại diện, đo queue wait, connection utilization, timeout và p95/p99; mức gate phụ thuộc SLO và rủi ro thay đổi.

### Tình huống G — False positive bảo mật

SAST báo một finding nghiêm trọng nhưng reviewer cho rằng code không thể đi tới nhánh đó. Tác giả muốn bỏ qua ngay.

**Câu hỏi:** Cần gì trước khi tạo ngoại lệ?

**Gợi ý:** Kiểm tra data flow, điều kiện kích hoạt, cấu hình, confidence và phạm vi phiên bản. Nếu xác nhận false positive, ghi lý do, owner và cách quản lý ngoại lệ theo policy; không tắt cả rule một cách tùy tiện.

### Tình huống H — Kết quả CI thuộc commit cũ

PR đã xanh, nhưng sau đó tác giả push thêm một commit thay đổi dependency. Nền tảng vẫn hiển thị các job trước đó là thành công.

**Câu hỏi:** Có thể merge ngay không?

**Gợi ý:** Không nếu kết quả không áp dụng cho revision cuối. Các gate cần thiết phải chạy lại hoặc được xác nhận trên commit/tổ hợp mã thực sự sẽ merge.

---

**Ghi nhớ:** Hãy tổ chức quality gate theo hướng **phản hồi nhanh trước, kiểm chứng sâu sau**, dựa trên chi phí và dependency thực tế. Đưa format, cấu hình, secret và compile lên sớm; dùng unit test và phân tích tĩnh để bắt lỗi gần logic; tiếp tục với integration, contract, E2E và performance khi phạm vi/rủi ro yêu cầu. Chạy song song các bước độc lập có kiểm soát, phân biệt **pass, fail, skipped và not run**, đồng thời quy định rõ gate nào blocking. Một pipeline tốt giúp nhóm **biết sớm điều gì sai, hiểu vì sao sai và có bằng chứng phù hợp trước khi merge hoặc release**.
