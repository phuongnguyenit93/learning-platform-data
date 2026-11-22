# Kiểm tra tại máy phát triển, trước hợp nhất và trên CI

Một lập trình viên thay đổi chính sách tính phí giao hàng. Test chạy trên máy cá nhân đều xanh, formatter không báo lỗi và bản build tạo được. Sau khi mở pull request, CI lại thất bại vì một test phụ thuộc múi giờ mặc định của máy chạy. Nhóm sửa test, đẩy commit mới, nhưng một lỗi khác chỉ xuất hiện khi hai yêu cầu cập nhật cùng một bản ghi. Nếu mọi kiểm tra chỉ được chạy vào cuối quy trình, phản hồi đến muộn và việc tìm nguyên nhân tốn nhiều công sức.

Một quy trình chất lượng hiệu quả phân bổ kiểm tra vào **những thời điểm khác nhau**: ngay khi lập trình viên đang làm việc, trước khi hợp nhất thay đổi và trong các pipeline CI sau đó. Mỗi vòng có mục tiêu, thời gian phản hồi và phạm vi khác nhau. Cách tổ chức tốt giúp phát hiện lỗi sớm, bảo vệ nhánh chính và vẫn kiểm chứng được những rủi ro cần môi trường rộng hơn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Cổng chất lượng**, bài này tập trung vào cách phối hợp **kiểm tra tại máy phát triển, trước hợp nhất và trên CI**; lựa chọn kiểm tra phù hợp với rủi ro; giữ kết quả có thể tái hiện; và xử lý thất bại để cổng chất lượng trở thành công cụ hỗ trợ nhóm phát triển.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mục tiêu của vòng kiểm tra **local**, **pre-merge** và **CI sau hợp nhất/triển khai**.
- Chọn kiểm tra theo chi phí phản hồi, phạm vi và mức rủi ro thay vì chạy mọi thứ ở mọi nơi.
- Thiết kế quality gate với điều kiện rõ ràng về test, phân tích, bảo mật, review và khả năng tương thích.
- Sử dụng Java/JUnit 5 để minh họa cách kiểm tra thay đổi nghiệp vụ từ máy phát triển đến pipeline.
- Làm cho kết quả local và CI nhất quán bằng toolchain, dependency, cấu hình và dữ liệu kiểm thử có thể tái lập.
- Chẩn đoán test không ổn định, tránh để retry hoặc suppression che giấu lỗi thật.
- Đọc trạng thái pipeline và xử lý ngoại lệ cổng chất lượng có chủ sở hữu, lý do và thời hạn.

## 1. Vì sao cần nhiều vòng kiểm tra?

Không phải mọi lỗi đều có cùng cách phát hiện hoặc chi phí kiểm chứng.

- Lỗi định dạng và import dư có thể được phát hiện nhanh bằng formatter/linter ngay trong IDE.
- Lỗi logic ở giá trị biên có thể được phát hiện bằng unit test chạy trong vài giây.
- Lỗi truy vấn, transaction hoặc migration cần database thật hay môi trường tích hợp.
- Lỗi phân quyền có thể cần test qua HTTP và dữ liệu của nhiều người dùng.
- Hiệu năng, hành vi đồng thời hoặc khả năng phục hồi cần môi trường có tải và cấu hình gần thực tế.

Nếu chờ tới pipeline cuối cùng mới chạy tất cả, lập trình viên có thể nhận hàng chục lỗi sau một lần đẩy mã. Ngược lại, nếu bắt mỗi lần lưu file phải chạy toàn bộ test end-to-end, phản hồi sẽ chậm và người phát triển có xu hướng bỏ qua hoặc tìm cách né quy trình.

**Chiến lược nhiều vòng** cân bằng ba mục tiêu:

1. **Phản hồi nhanh:** phát hiện lỗi dễ sửa ngay tại nơi tạo ra thay đổi.
2. **Bảo vệ hợp nhất:** yêu cầu bằng chứng tối thiểu trước khi đưa mã vào nhánh dùng chung.
3. **Kiểm chứng hệ thống:** chạy các bài test và kiểm tra cần nhiều thành phần, môi trường hoặc dữ liệu hơn.

### Các vòng phản hồi

~~~text
LẬP TRÌNH VIÊN
    |
    v
LOCAL CHECKS
Format / compile / unit test / kiểm tra nhanh
    |
    v
PULL REQUEST
Review / test tích hợp / phân tích / security checks
    |
    v
PRE-MERGE QUALITY GATE
Các điều kiện bắt buộc đã đạt?
    |
    +---- Không đạt ----> Sửa và chạy lại trên commit mới
    |
    v
MERGE
    |
    v
CI SAU HỢP NHẤT
Full suite / package / migration / end-to-end
    |
    v
STAGING / RELEASE
Smoke test / kiểm tra cấu hình / canary
    |
    v
OBSERVABILITY
Theo dõi lỗi, hiệu năng và hành vi thực tế
~~~

CI là cơ chế tự động thực thi pipeline; nó có thể chạy **cả kiểm tra pre-merge và sau merge**. Vì vậy, “local, pre-merge, CI” không phải ba công cụ loại trừ nhau: local là môi trường phản hồi của người phát triển, còn CI là nơi chạy những điều kiện đã được nhóm thống nhất một cách nhất quán và có thể kiểm tra lại.

## 2. Kiểm tra tại máy phát triển (local checks)

Mục tiêu của vòng local là **phát hiện nhanh lỗi gần thời điểm viết mã**, khi người phát triển còn nhớ rõ ý định và có thể sửa ngay.

Các kiểm tra phù hợp:

| Kiểm tra | Mục đích | Đặc điểm |
| --- | --- | --- |
| Format/import | Chuẩn hóa cách trình bày, phát hiện import không dùng | Rất nhanh, có thể tích hợp IDE hoặc pre-commit |
| Compile/type check | Phát hiện lỗi cú pháp, kiểu và tham chiếu | Thường cần chạy sau khi đổi chữ ký hoặc kiểu |
| Unit test liên quan | Kiểm tra quy tắc vừa thay đổi | Nhanh, phạm vi nhỏ, dễ tái hiện |
| Lint/static analysis cơ bản | Phát hiện một số mẫu lỗi và quy ước | Phản hồi sớm, có thể cần cấu hình dự án |
| Diff hygiene | Phát hiện whitespace lỗi, file ngoài phạm vi hoặc thay đổi vô tình | Chi phí thấp |
| Test dữ liệu/biên | Kiểm tra giá trị đặc biệt gần logic đang sửa | Nên chạy ngay khi thay đổi hợp đồng |

### Ví dụ lệnh theo công cụ build

Nếu dự án Java dùng Gradle Wrapper và đã cấu hình task tương ứng:

~~~bash
./gradlew test
./gradlew check
~~~

`test` thường chạy các test được cấu hình cho source set test. `check` là lifecycle task để gom các kiểm tra xác minh đã được gắn vào dự án; task cụ thể phụ thuộc plugin và cấu hình build.

Nếu dự án dùng Maven Wrapper:

~~~bash
./mvnw test
./mvnw verify
~~~

`test` chạy test ở phase tương ứng; `verify` chạy các phase trước đó tới `verify` và các goal/plugin đã được cấu hình gắn vào lifecycle. Không nên mặc định một dự án có SAST, coverage hoặc formatter chỉ vì lệnh `verify` đã chạy.

Các lệnh trên là **ví dụ phổ biến**, không phải yêu cầu mọi repository đều phải dùng Gradle hoặc Maven. Hãy dùng wrapper và task đã được dự án định nghĩa, đồng thời công bố rõ kiểm tra nào thực sự được thực thi.

### Không cần chạy toàn bộ pipeline sau mỗi thay đổi nhỏ

Khi sửa một hàm tính phí thuần, có thể chạy test lớp chính sách trước. Khi đổi schema hoặc transaction, cần thêm test tích hợp phù hợp. Khi thay dependency hoặc cấu hình build, cần chạy những kiểm tra liên quan đến phạm vi đó.

Một nguyên tắc thực tế:

**Chạy vòng nhanh sau mỗi thay đổi nhỏ; chạy tập kiểm tra rộng hơn trước khi tạo hoặc cập nhật pull request.**

Tuy nhiên, test nhanh không được trở thành lý do bỏ qua kiểm tra quan trọng. Nếu thay đổi chạm tới quyền truy cập, tiền, dữ liệu bền vững hoặc concurrency, cần lập kế hoạch kiểm chứng tương xứng.

## 3. Kiểm tra trước hợp nhất (pre-merge checks)

Vòng pre-merge chạy trên thay đổi được đề xuất và tạo bằng chứng để quyết định có cho phép hợp nhất vào nhánh dùng chung hay không.

Thông thường, nó gồm:

- **Build và compile:** xác nhận thay đổi có thể tạo artifact theo cấu hình đã công bố.
- **Unit tests:** kiểm tra quy tắc mới, đường cũ liên quan và giá trị biên.
- **Integration/contract tests:** kiểm tra adapter, database, HTTP, queue hoặc thành phần liên quan.
- **Formatter/linter/static analysis:** áp dụng quy ước và phát hiện mẫu lỗi đã định nghĩa.
- **Security/dependency checks:** tìm secret, mẫu mã nguy hiểm và dependency có advisory.
- **Review:** người có trách nhiệm xem xét hợp đồng, thiết kế và rủi ro theo ngữ cảnh.
- **Migration/compatibility checks:** xác minh thay đổi schema, API và dữ liệu cũ nếu có.

Không phải PR nào cũng cần mọi loại test. Nhưng mỗi PR phải có **tập điều kiện phù hợp với loại rủi ro**, và quy trình cần chỉ rõ điều kiện nào là bắt buộc.

### Quality gate phải gắn với một commit cụ thể

Khi tác giả đẩy commit mới sau review, kết quả CI của commit cũ không tự chứng minh commit mới đạt. Các trạng thái bắt buộc nên gắn với **revision chính xác** được định hợp nhất. Nếu nhánh đích thay đổi và chính sách yêu cầu cập nhật với nhánh mới nhất, pipeline cần chạy lại theo quy tắc đó.

Một gate pre-merge minh họa:

| Điều kiện | Quy tắc có thể áp dụng |
| --- | --- |
| Build | Bắt buộc thành công trên toolchain đã công bố |
| Unit test | Tất cả test bắt buộc trong phạm vi PR đạt |
| Test liên quan rủi ro | Có test biên/đường lỗi cho hành vi được thay đổi |
| Integration test | Chạy khi thay đổi chạm adapter, persistence hoặc hợp đồng giữa dịch vụ |
| Static/security findings | Không có finding blocker đã xác nhận chưa được xử lý theo chính sách |
| Review | Đủ phê duyệt của người có trách nhiệm; yêu cầu chuyên môn khi thay đổi vùng nhạy cảm |
| Migration | Có kiểm tra tương thích và trình tự triển khai nếu schema thay đổi |
| Nội dung PR | Nêu mục tiêu, phạm vi, bằng chứng và rủi ro còn lại |

Các ngưỡng như coverage, severity hoặc số approval phải được xác định theo **rủi ro và quy trình của dự án**. Một ngưỡng chung áp dụng bất kể loại thay đổi dễ dẫn đến việc tối ưu con số thay vì bảo vệ hành vi.

## 4. CI: chạy kiểm tra có thể tái lập và lưu bằng chứng

**Continuous Integration (CI)** tự động build và kiểm tra thay đổi khi có sự kiện như push, pull request hoặc merge. CI có ích vì mọi người dùng chung một môi trường chạy được khai báo, log tập trung và trạng thái có thể truy vết.

Một pipeline có thể chia thành các nhóm:

| Nhóm job | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Fast validation** | Checkout, xác định JDK, format check, compile | Báo lỗi cơ bản sớm |
| **Unit tests** | Test domain, utility, value objects | Kiểm chứng quy tắc nhỏ |
| **Static/security** | Lint, SAST, SCA, secret scan | Tìm mẫu rủi ro và vấn đề dependency |
| **Integration** | Database test, API contract, queue adapter | Kiểm chứng phối hợp giữa thành phần |
| **Packaging** | Build artifact, kiểm tra metadata, ký nếu cần | Tạo đầu ra có thể triển khai |
| **Extended tests** | End-to-end, performance, migration, resilience | Kiểm tra rủi ro rộng hơn |
| **Post-deploy** | Smoke test, canary, health checks | Xác nhận dịch vụ sau triển khai |

Các job độc lập có thể chạy song song để giảm thời gian chờ. Job cần kết quả của job khác phải có quan hệ phụ thuộc rõ; ví dụ integration test cần artifact đã build hoặc database test đã sẵn sàng.

### Ví dụ pipeline khái niệm

Sơ đồ sau mô tả **mối quan hệ giữa các nhóm kiểm tra**, không phải cú pháp YAML của một nhà cung cấp CI cụ thể:

~~~text
                 Push / Pull Request
                         |
                         v
                    Checkout
                         |
                         v
                   Build + Compile
                         |
              +----------+----------+
              |          |          |
              v          v          v
          Unit tests   Static     Dependency /
                       analysis   secret scan
              |          |          |
              +----------+----------+
                         |
                         v
                Integration tests
                         |
                         v
                Required PR checks
                         |
                  All required pass?
                    /         \
                  No           Yes
                  |             |
                  v             v
              Block merge    Allow merge
                                |
                                v
                         Post-merge CI
                                |
                                v
                     Package / Deploy staging
                                |
                                v
                       Smoke / Canary checks
~~~

Với pipeline thật, cần xác định rõ **job nào bắt buộc**, job nào cung cấp thông tin bổ sung, điều kiện bỏ qua hợp lệ và cách báo lỗi. Một job bị bỏ qua do điều kiện cấu hình không giống với job đã chạy và đạt.

## 5. Ví dụ xuyên suốt: thay đổi chính sách miễn phí vận chuyển

Giả sử sản phẩm có chính sách **minh họa**:

- Giao tiêu chuẩn miễn phí khi tổng tiền hàng **từ 500.000 VND trở lên**.
- Giao nhanh luôn tính phí 30.000 VND.
- Giao tiêu chuẩn dưới ngưỡng tính phí 20.000 VND.
- Tổng tiền âm và loại giao không hợp lệ phải bị từ chối.

Thay đổi ngưỡng miễn phí là một thay đổi nghiệp vụ nhỏ nhưng có **giá trị biên quan trọng**. Mục tiêu của các vòng kiểm tra là bắt lỗi nhanh tại local, xác minh trong PR và chạy lại trong môi trường CI thống nhất.

### 5.1. Mã Java 17

~~~java
public enum DeliveryType {
    STANDARD,
    EXPRESS
}
~~~

~~~java
import java.util.Objects;

public final class DeliveryFeePolicy {
    private static final long FREE_STANDARD_THRESHOLD_VND = 500_000;
    private static final long STANDARD_FEE_VND = 20_000;
    private static final long EXPRESS_FEE_VND = 30_000;

    public long calculateFee(long subtotalVnd, DeliveryType type) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(type, "type");

        if (type == DeliveryType.EXPRESS) {
            return EXPRESS_FEE_VND;
        }
        return subtotalVnd >= FREE_STANDARD_THRESHOLD_VND
            ? 0
            : STANDARD_FEE_VND;
    }
}
~~~

Các kiểu `public` cần đặt trong các file riêng theo tên kiểu; các đoạn mã ở đây minh họa nội dung của những file riêng trong cùng package.

### 5.2. Test giá trị biên bằng JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DeliveryFeePolicyTest {
    private final DeliveryFeePolicy policy = new DeliveryFeePolicy();

    @ParameterizedTest
    @CsvSource({
        "499999, STANDARD, 20000",
        "500000, STANDARD, 0",
        "500001, STANDARD, 0",
        "500000, EXPRESS, 30000"
    })
    void calculatesFeeAccordingToPolicy(
            long subtotalVnd, DeliveryType type, long expected) {
        assertEquals(expected, policy.calculateFee(subtotalVnd, type));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(
            IllegalArgumentException.class,
            () -> policy.calculateFee(-1, DeliveryType.STANDARD)
        );
        assertThrows(
            NullPointerException.class,
            () -> policy.calculateFee(100_000, null)
        );
    }
}
~~~

Expected value của test xuất phát từ **chính sách đã được xác nhận**, không được tính lại bằng cùng biểu thức của production code. Test ở đúng 500.000 VND bảo vệ ranh giới dễ nhầm giữa `>` và `>=`.

### 5.3. Phân bổ kiểm tra theo vòng

| Vòng | Việc nên chạy cho thay đổi này | Lý do |
| --- | --- | --- |
| Local | Format, compile, `DeliveryFeePolicyTest` | Phản hồi nhanh về cú pháp và quy tắc |
| Trước PR | Toàn bộ unit tests liên quan checkout/hóa đơn, static analysis | Kiểm tra tác động đến caller và mẫu lỗi |
| Pre-merge CI | Build sạch, unit suite, integration test phù hợp, security/dependency checks đã cấu hình, review | Cung cấp gate trên commit cụ thể |
| Sau merge | Full suite, đóng gói artifact, kiểm tra migration nếu có | Xác minh tích hợp rộng và đầu ra phát hành |
| Staging/release | Smoke test, đối chiếu kết quả checkout và hóa đơn trong dữ liệu thử | Kiểm chứng luồng gần môi trường thật |
| Sau triển khai | Theo dõi tỷ lệ lệch phí, lỗi checkout và phản hồi vận hành | Phát hiện sai lệch mà test chưa bao phủ |

Không phải mọi thay đổi hằng số đều cần chạy performance test hoặc toàn bộ end-to-end suite tại local. Nhưng nếu thay đổi có ảnh hưởng đến cách tính giá, dữ liệu lịch sử hoặc nhiều kênh bán hàng, các kiểm tra tích hợp và đối soát phù hợp vẫn cần thiết trước khi phát hành.

## 6. Chọn thứ tự chạy để phản hồi nhanh

Pipeline thường nên chạy **kiểm tra nhanh, ít tốn kém trước**, rồi tới những job dài hoặc cần môi trường đặc biệt. Nhưng có thể chạy song song các job độc lập.

Ví dụ thứ tự:

1. Checkout và thiết lập toolchain.
2. Kiểm tra format/compile nhanh.
3. Chạy unit tests.
4. Chạy static analysis và dependency scan song song khi phù hợp.
5. Khởi tạo dịch vụ phụ thuộc và chạy integration tests.
6. Build/package artifact.
7. Chạy extended tests theo loại thay đổi hoặc trước release.

Nếu một bước cơ bản thất bại, không cần tiêu tốn tài nguyên chạy những bước phụ thuộc vào đầu ra không hợp lệ. Tuy nhiên, pipeline có thể vẫn chạy song song SAST/SCA với unit test để tiết kiệm thời gian nếu các job độc lập.

### Tối ưu thời gian CI mà không giảm bằng chứng

- **Cache dependency** theo lockfile, wrapper và phiên bản toolchain; cache chỉ là tối ưu, không được biến cache cũ thành nguồn sự thật.
- **Chạy song song** test độc lập; cô lập tài nguyên dùng chung để tránh flaky tests.
- **Chia test theo suite** hoặc thời gian ước lượng, nhưng phải bảo đảm mọi suite bắt buộc đều được tổng hợp vào gate.
- **Chạy lại có mục đích** khi có lỗi hạ tầng đã được nhận diện; lưu cả kết quả lần đầu và các lần retry.
- **Dùng incremental checks** cho phản hồi nhanh nếu công cụ hỗ trợ, nhưng định kỳ vẫn cần full scan/full suite để phát hiện vấn đề ngoài tập thay đổi trực tiếp.
- **Tránh tạo môi trường mới không cần thiết** cho mỗi job nếu có thể dùng service/container đã được quản lý và cô lập đúng cách.

Một pipeline nhanh nhưng âm thầm bỏ qua test quan trọng không phải pipeline hiệu quả. Mục tiêu là **giảm thời gian chờ không cần thiết mà giữ nguyên phạm vi kiểm chứng đã cam kết**.

## 7. Làm cho local và CI nhất quán

“Máy tôi chạy được” thường xuất hiện khi môi trường local và CI khác nhau. Những khác biệt thường gặp:

| Nguồn khác biệt | Biểu hiện | Cách giảm sai khác |
| --- | --- | --- |
| JDK | Local dùng JDK mới, CI dùng bản cũ hoặc ngược lại | Công bố toolchain/JDK được hỗ trợ, dùng cấu hình build thống nhất |
| Build tool | Mỗi người cài Gradle/Maven phiên bản khác | Dùng Gradle Wrapper/Maven Wrapper và kiểm tra wrapper |
| Dependency | Local có thư viện trong cache, CI tải phiên bản khác | Khai báo phiên bản rõ, dependency locking khi phù hợp, kiểm tra checksum/repository |
| Timezone/locale | Test ngày giờ hoặc định dạng số khác kết quả | Cố định timezone/locale trong test; dùng kiểu thời gian rõ nghĩa |
| Filesystem/OS | Khác đường dẫn, phân biệt hoa thường, line ending | Dùng API portable, fixture riêng, chạy trên nền tảng hỗ trợ |
| Biến môi trường | Local có cấu hình bí mật hoặc service endpoint sẵn | Khai báo cấu hình test tường minh, dùng secret store an toàn |
| Database | Phiên bản, collation, isolation khác | Chạy integration test với phiên bản và cấu hình phù hợp |
| Thứ tự/đồng thời | Test chỉ đạt khi chạy riêng hoặc theo một thứ tự | Cô lập fixture, không phụ thuộc thứ tự, kiểm tra song song có kiểm soát |

### Dùng test độc lập với thời gian thực

Test không nên giả định máy sẽ chạy tiếp sau đúng một khoảng ngủ. Nếu nghiệp vụ phụ thuộc thời gian, truyền `Clock` vào thành phần cần kiểm tra và dùng `Clock.fixed` trong test. Nếu cần chờ bất đồng bộ, chờ Future hoặc tín hiệu hoàn thành với timeout hữu hạn.

### Dùng dữ liệu kiểm thử có thể tái tạo

Test nên tự tạo dữ liệu cần thiết, có định danh riêng và dọn tài nguyên theo vòng đời. Tránh dùng cùng một tài khoản, mã đơn hoặc file cố định giữa các job chạy song song. Với test ngẫu nhiên, lưu seed và đầu vào gây lỗi để có thể tái hiện.

### Không đưa bí mật production vào pipeline kiểm thử

Pull request từ nhánh ngoài hoặc fork có thể chạy trong môi trường không đáng tin cậy. Không nên cấp secret triển khai production cho job chỉ cần compile/unit test. Phân tách quyền của workflow và chỉ cấp credential cần thiết ở job, môi trường và sự kiện được phép.

## 8. Xử lý test không ổn định và thất bại của pipeline

Một test đỏ trên CI có thể là:

- Lỗi thật của sản phẩm.
- Test có phụ thuộc thời gian, thứ tự, trạng thái dùng chung hoặc scheduling.
- Môi trường/fixture không ổn định.
- Dịch vụ phụ thuộc bị lỗi hoặc cấu hình sai.
- Tài nguyên runner không đủ.

Không nên kết luận ngay “CI bị lỗi” chỉ vì chạy lại thấy xanh.

Quy trình xử lý:

1. Giữ log và kết quả **lần chạy đầu tiên**.
2. Ghi commit, runner, JDK, OS, timezone, dependency và service version.
3. Tái hiện riêng test và trong suite để kiểm tra thứ tự hoặc trạng thái chia sẻ.
4. So sánh local với CI bằng cùng toolchain/cấu hình khi có thể.
5. Xác định test đang kiểm tra hợp đồng nào; nếu lỗi phản ánh bug sản phẩm, tạo test hồi quy.
6. Nếu là lỗi hạ tầng, ghi bằng chứng, phạm vi ảnh hưởng và người xử lý.
7. Chỉ retry theo chính sách rõ ràng; lưu trạng thái lần đầu và các lần tiếp theo.

### Quarantine không đồng nghĩa đã sửa

Đôi khi một test không ổn định phải được tạm cách ly khỏi gate để nhóm có thể tiếp tục công việc. Khi đó cần:

- Lưu finding và nguyên nhân nghi ngờ.
- Chỉ định người phụ trách.
- Có thời hạn xem lại.
- Tiếp tục thu thập kết quả nếu có thể.
- Đánh giá mức rủi ro nếu test đang bảo vệ thanh toán, quyền truy cập hoặc dữ liệu quan trọng.

Không được xóa assertion, tăng timeout vô hạn hoặc retry không giới hạn chỉ để pipeline xanh. **Gate xanh sau retry vẫn cần được diễn giải cùng kết quả thất bại ban đầu.**

## 9. Thiết kế quality gate: điều kiện nào thực sự chặn merge?

Một quality gate tốt có **điều kiện bắt buộc, phạm vi, bằng chứng, người quyết định và quy trình ngoại lệ** rõ ràng.

### Gate kỹ thuật và gate theo rủi ro

| Điều kiện | Có thể làm gate bắt buộc khi... | Cần tránh |
| --- | --- | --- |
| Build/compile | Mọi thay đổi phải tạo artifact hợp lệ | Cho qua lỗi compile vì test job khác xanh |
| Unit tests | Các test bắt buộc trong phạm vi đã chạy | Bỏ qua test thất bại không có lý do |
| Integration tests | Thay đổi ảnh hưởng persistence/API/adapter | Chạy quá rộng cho mọi thay đổi khiến phản hồi chậm mà không tăng bằng chứng |
| Security findings | Có finding blocker/critical đã xác nhận theo chính sách | Chặn mọi cảnh báo thấp hoặc suppress hàng loạt |
| Coverage | Có mục tiêu được định nghĩa rõ và đo đúng phạm vi | Coi một phần trăm duy nhất là bằng chứng đúng đắn |
| Review approval | Thay đổi cần người chịu trách nhiệm đánh giá | Approval không gắn với commit cuối cùng |
| Migration/compatibility | Thay schema hoặc hợp đồng client | Chỉ test schema mới mà bỏ dữ liệu và ứng dụng cũ |
| Artifact provenance | Có yêu cầu kiểm soát nguồn build và phụ thuộc | Triển khai artifact không rõ commit/cấu hình |

### Gate không nên chỉ là một ngưỡng coverage

Ví dụ, yêu cầu “coverage ít nhất 80%” có thể khiến nhóm thêm test chỉ gọi phương thức mà không assert. Một thay đổi thanh toán có thể đạt coverage cao nhưng thiếu test cho timeout sau khi đối tác đã xử lý.

Nếu dùng coverage, hãy xác định:

- Loại coverage (line, branch, condition...) và công cụ đo.
- Phạm vi tính: toàn dự án, module hay phần mã mới.
- Cách xử lý mã sinh tự động, adapter hoặc mã không thể kiểm tra hợp lý.
- Những test có assertion và expected xuất phát từ hợp đồng nào.
- Cách review ngoại lệ và xu hướng giảm theo thời gian.

**Coverage hỗ trợ đánh giá phạm vi test; nó không thay thế chất lượng oracle và lựa chọn tình huống.**

### Ngoại lệ gate cần có kiểm soát

Một ngoại lệ có thể cần thiết khi dịch vụ phụ thuộc ngừng hoạt động, runner gặp sự cố hoặc một cảnh báo đã được điều tra nhưng công cụ chưa hỗ trợ cấu hình chính xác. Ghi nhận tối thiểu:

| Trường | Nội dung cần có |
| --- | --- |
| Điều kiện được miễn | Job/rule/commit cụ thể |
| Lý do | Bằng chứng vì sao không thể đạt gate trong lần này |
| Rủi ro còn lại | Hành vi nào chưa được kiểm chứng |
| Người chấp thuận | Chủ sở hữu có thẩm quyền theo quy trình |
| Biện pháp thay thế | Test thủ công, kiểm tra ở staging hoặc hạn chế triển khai |
| Thời hạn | Khi nào phải xử lý hoặc xem lại |

Ngoại lệ không nên trở thành đường tắt mặc định. Với rủi ro dữ liệu, tiền hoặc quyền truy cập nghiêm trọng, cần quyết định rõ có thể trì hoãn phát hành hay phải giảm thiểu bằng biện pháp khác.

## 10. Pre-commit, pre-push và CI: dùng hook đúng chỗ

Git hooks có thể chạy formatter, lint hoặc test nhanh trước khi tạo commit/push. Chúng giúp người phát triển phát hiện lỗi sớm, nhưng có những giới hạn:

- Hook có thể không được cài đặt hoặc bị bỏ qua bởi một số cách commit.
- Môi trường máy cá nhân không đồng nhất.
- Chạy test nặng trước mỗi commit có thể làm giảm năng suất.
- Hook không thay thế status check bắt buộc trên máy chủ quản lý repository.

Vì vậy:

- Dùng hook cho kiểm tra **nhanh, xác định và có thể chạy thường xuyên**.
- Dùng CI để chạy **bộ kiểm tra bắt buộc, thống nhất và có log**.
- Dùng branch protection hoặc quy tắc tương đương để chỉ cho phép merge khi required checks và review đã đạt.
- Nếu CI có thể chạy lại trên commit khác, phải gắn kết quả với đúng commit sẽ merge.

Không nên đặt logic bảo vệ quan trọng chỉ trong hook local mà không có kiểm tra phía máy chủ.

## 11. Theo dõi sức khỏe của chính pipeline

Một pipeline cũng là phần mềm cần được cải thiện. Nhóm có thể theo dõi:

| Chỉ số pipeline | Câu hỏi |
| --- | --- |
| Thời gian feedback trung vị và p95 | Lập trình viên phải chờ bao lâu ở lần chạy thường và trường hợp chậm? |
| Tỷ lệ job thất bại do mã so với hạ tầng | Có phân loại nguyên nhân hay mọi lỗi đều bị tính như bug? |
| Tỷ lệ flaky test | Test nào dao động và có chủ sở hữu sửa không? |
| Số lần retry | Retry có đang che giấu lỗi thường xuyên? |
| Thời gian queue | Runner có thiếu tài nguyên hoặc phân bổ không hợp lý? |
| Tỷ lệ gate bị bypass | Ngoại lệ có tăng và có được xem lại? |
| Tỷ lệ lỗi lọt qua sau merge | Gate có bỏ sót lớp rủi ro quan trọng nào? |
| Độ phủ pipeline | Các nhánh/module quan trọng có thực sự chạy kiểm tra bắt buộc? |

Những chỉ số này giúp trả lời **quy trình kiểm tra có đang hỗ trợ nhóm không**, không chỉ đo mã nguồn. Ví dụ, CI quá chậm có thể khiến người phát triển gom nhiều thay đổi vào một PR, làm review khó hơn. Flaky tests cao có thể khiến nhóm bỏ qua cả cảnh báo thật. Một gate quá dễ bị bypass không còn tạo ra bảo đảm như mong muốn.

Không nên tối ưu chỉ một con số. Rút thời gian CI bằng cách bỏ integration test quan trọng có thể làm tăng chi phí sự cố; tăng số job mà không cải thiện khả năng chẩn đoán chỉ khiến pipeline phức tạp hơn.

## 12. Checklist thiết kế các vòng kiểm tra

### Local

- [ ] Có lệnh nhanh và ổn định để format, compile và chạy unit tests liên quan.
- [ ] Toolchain và dependency có cách thiết lập thống nhất.
- [ ] Lỗi hiển thị gần vị trí thay đổi, dễ tái hiện.
- [ ] Hook chỉ chặn những kiểm tra phù hợp với tần suất chạy cao.

### Trước hợp nhất

- [ ] CI chạy trên commit cụ thể của pull request.
- [ ] Required checks được cấu hình rõ và có kết quả dễ đọc.
- [ ] Test phù hợp với hợp đồng, giá trị biên và đường lỗi của thay đổi.
- [ ] Review xem xét thiết kế, quyền truy cập, dữ liệu, concurrency và tương thích khi liên quan.
- [ ] Cảnh báo bảo mật và dependency có trạng thái xác minh, không bị bỏ qua tùy tiện.
- [ ] Ngoại lệ có người chấp thuận, lý do và thời hạn.

### Sau hợp nhất và triển khai

- [ ] Full suite hoặc test mở rộng được chạy theo chiến lược đã định.
- [ ] Artifact có thể truy vết tới commit và cấu hình build.
- [ ] Smoke/canary test xác minh luồng quan trọng ở môi trường triển khai.
- [ ] Có telemetry và người chịu trách nhiệm xử lý tín hiệu sau phát hành.
- [ ] Kết quả flaky, lỗi hạ tầng và lỗi sản phẩm được phân loại riêng.

## 13. Bài tập tình huống

Một nhóm Java thay đổi logic tính phí và mở PR. Báo cáo ban đầu:

~~~text
Local:
  - Format: PASS
  - Compile: PASS
  - Unit tests: PASS (chỉ chạy một lớp test mới)

Pre-merge CI:
  - Build: PASS
  - Unit suite: PASS
  - Integration test: FAIL (database migration không tương thích)
  - SAST: PASS
  - Review: 1 approval

Sau khi retry:
  - Integration test: PASS
~~~

Giả sử thay đổi thêm một cột bắt buộc vào bảng hóa đơn, trong khi phiên bản ứng dụng cũ vẫn đang chạy trong quá trình triển khai cuốn chiếu.

**Câu hỏi A.** Có thể merge chỉ vì lần retry integration test đã xanh không? Cần điều tra gì?

**Câu hỏi B.** Vì sao local unit tests xanh không đủ chứng minh migration an toàn?

**Câu hỏi C.** Nên kiểm tra điều gì trước merge và điều gì sau merge/ở staging?

**Câu hỏi D.** Nếu pipeline đang quá chậm, có thể bỏ integration test này khỏi gate không?

### Gợi ý đáp án

**A.** Chưa. Cần lưu lỗi đầu tiên, xem nguyên nhân migration không tương thích và xác định lần retry thành công vì điều kiện môi trường thay đổi hay vì lỗi thực sự không ổn định. Nếu migration có thể làm ứng dụng cũ lỗi khi deploy cuốn chiếu, đây là rủi ro tương thích cần giải quyết trước khi merge/phát hành theo chính sách.

**B.** Unit test thường không chạy database thật và không kiểm tra dữ liệu cũ, schema, constraint hoặc thứ tự migration. Nó có thể chứng minh quy tắc tính phí trong một lớp, nhưng không chứng minh hai phiên bản ứng dụng cùng tương tác được với schema trong giai đoạn chuyển đổi.

**C.** Trước merge cần kiểm tra migration trên database phù hợp, dữ liệu đại diện, ứng dụng cũ/mới cùng tồn tại và hợp đồng ghi/đọc. Ở staging cần chạy luồng hóa đơn, smoke test và xác minh artifact/config. Sau triển khai cần theo dõi lỗi truy vấn, lỗi ghi hóa đơn và khả năng rollback hoặc hoàn tất migration.

**D.** Không nên bỏ một kiểm tra quan trọng chỉ để giảm thời gian. Có thể tối ưu fixture, cache, song song job độc lập, chạy test theo phạm vi PR và duy trì full test ở giai đoạn phù hợp. Nếu buộc phải miễn tạm thời, cần đánh giá rủi ro, người chấp thuận, biện pháp thay thế và thời hạn.

## Ghi nhớ

**Kiểm tra tại local, trước hợp nhất và trên CI tạo thành các vòng phản hồi bổ sung cho nhau.** Local giúp phát hiện lỗi nhanh khi đang lập trình; pre-merge bảo vệ nhánh dùng chung bằng những điều kiện bắt buộc; CI sau hợp nhất, staging và quan sát vận hành kiểm chứng phạm vi hệ thống rộng hơn.

Một cổng chất lượng tốt không phải là chạy mọi kiểm tra ở mọi thời điểm. Nó chọn **bằng chứng phù hợp với rủi ro**, giữ môi trường có thể tái lập, gắn kết quả với đúng commit và có cách xử lý thất bại minh bạch. Mục tiêu cuối cùng là phát hiện vấn đề sớm, bảo vệ hành vi quan trọng và giúp nhóm phát triển thay đổi mã nguồn với sự tự tin dựa trên bằng chứng.
