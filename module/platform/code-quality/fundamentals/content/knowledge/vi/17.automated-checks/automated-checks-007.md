# Phân biệt vai trò của công cụ với tiêu chí chất lượng

> **Chương:** Kiểm tra tự động  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tiêu chí chất lượng** (điều hệ thống cần đáp ứng), **quy tắc kiểm tra** (điều có thể xác minh) và **công cụ** (phương tiện thu thập bằng chứng).
2. Giải thích chính xác vai trò và giới hạn của formatter, linter, phân tích tĩnh, kiểm tra kiểu, kiểm thử tự động, đo coverage, dependency scanner, công cụ bảo mật, công cụ đo hiệu năng và CI.
3. Đọc một kết quả “build xanh” đúng ngữ cảnh: **những kiểm tra nào đã chạy, với phạm vi và giả định nào**, thay vì suy ra “mã nguồn không có lỗi”.
4. Chuyển một mục tiêu mơ hồ như “dễ bảo trì”, “an toàn” hoặc “đủ nhanh” thành các **hợp đồng có thể kiểm tra**, bằng chứng phù hợp và rủi ro còn lại.
5. Xử lý cảnh báo, false positive, false negative, ngưỡng chất lượng và ngoại lệ có kiểm soát mà không biến chỉ số thành mục tiêu duy nhất.
6. Thiết kế một quy trình kiểm tra tự động có **phản hồi đủ sớm**, khả năng chẩn đoán và quyết định phát hành dựa trên rủi ro, kèm kiểm chứng của con người ở những nơi máy chưa thể kết luận.

## 1. Công cụ là phương tiện; chất lượng là điều cần đạt

Một nhóm Java cấu hình formatter, Checkstyle, unit test và công cụ quét phụ thuộc. Pipeline CI báo thành công. Sau khi phát hành, API lại tính sai số tiền ưu đãi cho khách có đơn **đúng bằng** ngưỡng giảm giá.

Tình huống này không nhất thiết chứng minh các công cụ hoạt động sai. Có thể tất cả đã làm đúng **việc mà chúng được thiết kế và cấu hình để làm**:

- Formatter đảm bảo văn bản mã theo quy tắc trình bày.
- Linter kiểm tra một tập luật về style hoặc cấu trúc.
- Trình biên dịch xác minh mã hợp lệ theo ngôn ngữ và hệ kiểu.
- Unit test kiểm tra những trường hợp và kỳ vọng được viết.
- Công cụ quét phụ thuộc đối chiếu thư viện với nguồn dữ liệu rủi ro đã biết.

Không công cụ nào tự biết rằng **đúng ngưỡng 1.000.000 VND cũng phải được giảm 10%**, nếu đặc tả đó chưa được thể hiện bằng test, hợp đồng hoặc cơ chế kiểm tra thích hợp.

**Tiêu chí chất lượng** là yêu cầu về mã hoặc hành vi hệ thống mà nhóm cần bảo vệ: tính đúng đắn, độ tin cậy, bảo mật, khả năng đọc, khả năng thay đổi, hiệu năng, khả năng sử dụng tài nguyên, khả năng vận hành... **Công cụ kiểm tra** cung cấp tín hiệu rằng một phần tiêu chí đã được đáp ứng, nhưng tín hiệu phải được diễn giải theo **phạm vi công cụ và tập quy tắc thực sự chạy**.

> **“Được công cụ chấp nhận” không đồng nghĩa “đạt mọi tiêu chí chất lượng”.** Ngược lại, một cảnh báo tự động chưa chắc đã chứng minh mã có lỗi thật; cần xác minh và quyết định theo ngữ cảnh.

### Ba tầng không nên đánh đồng

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Mục tiêu chất lượng** | Hệ thống cần có thuộc tính gì? | Khách không bị tính sai tiền |
| **Tiêu chí/hợp đồng có thể kiểm chứng** | Đúng nghĩa là gì, trong phạm vi nào? | VIP có tổng từ 1.000.000 VND được giảm 10% theo quy tắc làm tròn đã xác nhận |
| **Bằng chứng và công cụ** | Ta đo hoặc kiểm tra thế nào? | JUnit kiểm tra đúng ngưỡng, trường hợp biên và dữ liệu lớn; test tích hợp kiểm tra số tiền đưa tới cổng thanh toán |

Công cụ được chọn **sau khi** đã hiểu điều cần bảo vệ, không phải ngược lại. Việc “có sẵn công cụ A” không tự làm cho những thứ A đo được trở thành toàn bộ định nghĩa chất lượng.

## 2. Từ mục tiêu mơ hồ đến tiêu chí có thể xác minh

Các câu như “code sạch”, “hệ thống bảo mật”, “API nhanh” hữu ích để định hướng nhưng chưa đủ để thiết kế phép kiểm.

Hãy làm rõ:

1. **Đối tượng:** phương thức, mô-đun, API, dữ liệu, pipeline hay hành trình người dùng nào?
2. **Hành vi mong đợi:** điều gì được phép, phải xảy ra hoặc không được xảy ra?
3. **Điều kiện:** đầu vào, trạng thái, tải, quyền truy cập, môi trường và phiên bản nào?
4. **Ranh giới quan sát:** nơi nào có thể kiểm chứng đầu ra, tác dụng phụ hoặc vi phạm?
5. **Bằng chứng:** test, static rule, review, benchmark hay telemetry nào trả lời câu hỏi?
6. **Giới hạn:** điều gì chưa được kiểm tra, hoặc kết quả phụ thuộc giả định nào?
7. **Cách xử lý:** ai điều tra, sửa, chấp nhận tạm thời hoặc thay đổi quy tắc khi phát hiện vấn đề?

Ví dụ chuyển mục tiêu thành tiêu chí:

| Mục tiêu | Tiêu chí rõ hơn | Bằng chứng phù hợp |
| --- | --- | --- |
| “Giá tính đúng” | Tổng và giảm giá tuân chính sách tại ngưỡng, số âm, số lớn, làm tròn | Unit test, test property/biên; integration test tại ranh giới thanh toán |
| “API an toàn” | Người dùng chỉ đọc được đơn thuộc quyền và tenant hợp lệ | Kiểm thử quyền âm tính qua API và DB, review chính sách |
| “Code dễ đọc” | Tên thể hiện đơn vị và vai trò; các hợp đồng lỗi nhất quán | Formatter/linter hỗ trợ một phần; code review và ví dụ quy ước |
| “Đáng tin cậy khi lỗi” | Timeout không bị hiểu thành không tìm thấy; retry không nhân đôi giao dịch | Unit/component test, fault injection, integration test |
| “Đáp ứng nhanh” | p95 latency dưới ngưỡng đã thống nhất tại tải và tỷ lệ lỗi quy định | Load test có workload rõ, metrics/tracing |
| “Không dùng thư viện có rủi ro vượt ngưỡng” | Phụ thuộc được kiểm tra theo advisory và chính sách xử lý cụ thể | SCA/SBOM, kiểm tra phạm vi ảnh hưởng và bản vá |

Các giá trị ngưỡng phải dựa trên yêu cầu sản phẩm và bối cảnh; **không có một con số coverage, số cảnh báo hay p95 mặc định phù hợp với mọi dự án**.

## 3. Bản đồ vai trò và giới hạn của các nhóm công cụ

| Nhóm công cụ/biện pháp | Giỏi phát hiện hoặc thực thi | Thường **không** chứng minh |
| --- | --- | --- |
| **Formatter** | Định dạng, khoảng trắng, import theo cấu hình | Thuật toán đúng, dữ liệu an toàn, kiến trúc phù hợp |
| **Linter/style checker** | Quy ước đặt tên, cấu trúc và một số mẫu dễ lỗi | Hợp đồng nghiệp vụ được thực hiện đầy đủ |
| **Compiler/type checker** | Cú pháp, kiểu, lời gọi hợp lệ theo quy tắc ngôn ngữ | Dữ liệu không-null tại mọi ranh giới, xử lý lỗi đúng nghiệp vụ |
| **Static analysis** | Mẫu lỗi, luồng dữ liệu và vi phạm quy tắc có thể phân tích | Mọi đường thực thi và mọi nguy cơ đã được bao phủ |
| **Unit/component tests** | Hành vi của logic hoặc thành phần trên các input đã chọn | Database, mạng, cấu hình và client thật luôn đúng |
| **Integration/contract tests** | Giao tiếp, schema, mapping, ràng buộc thực | Tất cả tải, trạng thái cạnh tranh hoặc luồng người dùng |
| **E2E tests** | Hành trình qua nhiều thành phần đã cấu hình | Mọi giá trị biên và mọi lỗi hạ tầng |
| **Coverage/mutation tools** | Vùng mã được chạy; khả năng test phát hiện một số lỗi nhân tạo | Bằng chứng tuyệt đối về độ đúng hoặc không còn lỗi |
| **SAST/secret scanner** | Mẫu nguy cơ bảo mật trong mã, dấu hiệu bí mật bị đưa vào repository | Mọi lỗ hổng nghiệp vụ hoặc mọi bí mật không bao giờ bị lộ |
| **SCA/dependency scanner** | Thư viện, phiên bản, advisory và chính sách thành phần | Rủi ro runtime đã được khai thác hay toàn hệ thống an toàn |
| **Benchmark/profiler/load tools** | Chi phí cục bộ, đường nóng, latency, throughput, mức bão hòa | Mã đúng nghiệp vụ hoặc kết quả đại diện cho mọi môi trường |
| **CI/quality gate** | Tự động chạy những bước đã cấu hình và chặn điều kiện định sẵn | Những bước chưa được định nghĩa cũng đã được kiểm tra |

**Cùng một công cụ có thể hỗ trợ nhiều tiêu chí**, và một tiêu chí quan trọng thường cần nhiều nguồn bằng chứng. Không nên chọn công cụ chỉ qua nhãn “code quality”; hãy xem **những quy tắc nào được bật, kết quả quan sát được là gì và lỗ hổng nào còn lại**.

### Sơ đồ quan hệ đúng

~~~mermaid
flowchart TD
    Q["Mục tiêu chất lượng"] --> C["Hợp đồng / tiêu chí rõ ràng"]
    C --> R["Rủi ro và trường hợp cần kiểm tra"]
    R --> T["Công cụ + kiểm thử + review phù hợp"]
    T --> E["Kết quả và bằng chứng"]
    E --> D{"Đủ cho quyết định hiện tại?"}
    D -->|"Có"| A["Chấp nhận trong phạm vi đã xác minh"]
    D -->|"Chưa"| G["Bổ sung kiểm tra / làm rõ tiêu chí"]
    G --> R
    E -. "Không bảo đảm mọi lỗi đã được tìm ra" .-> L["Rủi ro còn lại"]
~~~

Một dashboard xanh chỉ là một phần của nút **“Kết quả và bằng chứng”**, không phải đích cuối cùng của sơ đồ.

## 4. Formatter và linter: làm giảm nhiễu, không thay thế thiết kế

Formatter như một Java formatter đã được nhóm chọn có thể chuẩn hóa dấu cách, xuống dòng và nhiều lựa chọn trình bày. Khi IDE và CI dùng cùng cấu hình, pull request thường ít tranh luận hình thức hơn.

Một linter hoặc style checker có thể thêm quy tắc: tên biến, cách tổ chức import, giới hạn một số cấu trúc, tránh mẫu mã dễ gây nhầm lẫn. Tuy nhiên:

~~~java
static long applyVipDiscount(long subtotalVnd, boolean vip) {
    if (vip && subtotalVnd > 1_000_000L) {
        return subtotalVnd - subtotalVnd / 10;
    }
    return subtotalVnd;
}
~~~

Đoạn mã hoàn toàn có thể **được định dạng đẹp, biên dịch được và qua nhiều luật style**. Nếu chính sách yêu cầu giảm từ **đúng 1.000.000 VND trở lên**, dấu `>` phải là `>=`. Formatter không có kiến thức này.

### Khi formatter/linter thực sự hữu ích

- Giảm số khác biệt không có ý nghĩa trong review.
- Giúp người mới nhận ra cách tổ chức thường dùng trong repository.
- Tự động phát hiện một số vi phạm lặp lại, trước khi reviewer mất thời gian.
- Tạo quy tắc chung về bố cục và một số pattern dễ gây lỗi.

### Khi áp dụng có thể gây hại

- Format cả nghìn file trong cùng PR sửa một lỗi quan trọng, khiến thay đổi hành vi bị che trong diff lớn.
- Đặt ngưỡng độ dài phương thức cứng nhắc rồi buộc tách một thuật toán gắn kết thành nhiều hàm chỉ để hết cảnh báo.
- Cấm mọi exception hoặc mọi `Optional` bất chấp ngữ nghĩa của từng API.
- Tự động đổi tên field public để hợp style nhưng phá hợp đồng JSON hoặc SDK đang dùng.

**Nguyên tắc:** chuẩn hóa hình thức khi có thể tự động hóa, nhưng **đánh giá chất lượng thiết kế bằng mục đích và hợp đồng thực**, không bằng việc “linter hết báo đỏ”.

## 5. Biên dịch và phân tích tĩnh: bằng chứng theo mô hình của công cụ

Trình biên dịch Java kiểm tra cú pháp, kiểu tĩnh và nhiều quy tắc của ngôn ngữ. Static analyzer có thể dựa trên AST, bytecode hoặc phân tích luồng dữ liệu để phát hiện mẫu nguy cơ. Tín hiệu này hữu ích vì không cần chạy toàn bộ ứng dụng.

Một số vấn đề có thể được phát hiện hoặc cảnh báo, tùy cấu hình và khả năng công cụ:

- Tham chiếu có thể null, phép gán hoặc giá trị trả về trái hợp đồng chú thích nullability.
- Tài nguyên không được đóng ở một số đường thực thi.
- Điều kiện có vẻ luôn đúng/sai, đoạn mã không thể tới.
- So sánh hoặc dùng API có pattern lỗi thường gặp.
- Mẫu nguy cơ bảo mật như dữ liệu không tin cậy đi vào API nhạy cảm.
- Phụ thuộc kiến trúc trái quy tắc module.

Nhưng mô hình phân tích có giới hạn: reflection, dynamic dispatch, native code, runtime configuration, thư viện bên ngoài, dữ liệu thực và hành vi phân tán có thể khiến phân tích thiếu hoặc không đủ chính xác.

### Mã hợp lệ về kiểu vẫn có thể sai hợp đồng

~~~java
static boolean canReadOrder(
        String actorId,
        String ownerId,
        boolean isLoggedIn
) {
    return isLoggedIn; // Sai nếu hợp đồng còn yêu cầu actorId == ownerId.
}
~~~

Đoạn mã compile được; tất cả kiểu đều đúng. Nhưng chức năng **xác thực** đã bị nhầm với **phân quyền theo đối tượng**. Một static rule chung khó chứng minh đây là lỗi nếu không có mô hình chính sách, hợp đồng hoặc test tương ứng.

Một số kiểm tra chính sách có thể tự động hóa bằng rule có mục tiêu, nhưng không nên mặc định công cụ phân tích tĩnh nào cũng hiểu toàn bộ quan hệ sở hữu và quyền trong ứng dụng.

### Cảnh báo không giống lỗi đã chứng minh

Một cảnh báo có thể là:

- **True positive:** phát hiện chính xác một vấn đề có ý nghĩa.
- **False positive:** mô hình công cụ báo nguy cơ nhưng hợp đồng thực khiến đường đó không thể xảy ra hoặc đã có biện pháp khác.
- **False negative:** lỗi có thật nhưng công cụ không phát hiện.
- **Thiếu cấu hình/phạm vi:** công cụ chưa quét file, module, phiên bản hoặc loại lỗi liên quan.

Nếu công cụ không báo gì, kết luận phù hợp là **“không phát hiện vi phạm theo cấu hình và phạm vi đã chạy”**, không phải “mọi lỗi đã được loại bỏ”.

## 6. Kiểm thử tự động: giả thuyết và kỳ vọng quan trọng hơn số lượng test

Một test được viết từ **đặc tả sai** có thể chạy xanh và củng cố lỗi. Một test không có assertion có thể tăng số lượng test hoặc coverage mà không kiểm tra kết quả quan trọng.

Ví dụ hoàn chỉnh Java cho chính sách giá **minh họa**:

- Tổng tiền bằng số nguyên VND và không âm.
- Khách VIP có tổng từ **1.000.000 VND trở lên** được giảm 10%.
- Tiền giảm lấy phần nguyên của `subtotal / 10`.
- Kết quả còn lại không âm trong miền đầu vào hợp lệ.

~~~java
final class VipPricing {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    private VipPricing() {}

    static long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            return subtotalVnd - subtotalVnd / 10;
        }

        return subtotalVnd;
    }
}
~~~

Kiểm thử JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class VipPricingTest {
    @Test
    void vipAtThresholdReceivesDiscount() {
        assertEquals(900_000L,
                VipPricing.amountDueVnd(1_000_000L, true));
    }

    @Test
    void vipBelowThresholdDoesNotReceiveDiscount() {
        assertEquals(999_999L,
                VipPricing.amountDueVnd(999_999L, true));
    }

    @Test
    void nonVipNeverReceivesVipDiscount() {
        assertEquals(1_500_000L,
                VipPricing.amountDueVnd(1_500_000L, false));
    }

    @Test
    void usesTheSpecifiedIntegerRoundingRule() {
        assertEquals(900_005L,
                VipPricing.amountDueVnd(1_000_005L, true));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> VipPricing.amountDueVnd(-1L, true));
    }
}
~~~

Nếu lập trình viên sửa điều kiện `>=` thành `>`, test ở đúng ngưỡng sẽ phát hiện. **Điểm quyết định không nằm ở JUnit tự hiểu nghiệp vụ**, mà ở việc người viết test đã thể hiện yêu cầu bằng đầu vào và kỳ vọng chính xác.

### Bằng chứng của bộ test này có giới hạn

Test có thể xác nhận công thức trên những trường hợp đã chọn. Nó **chưa chứng minh**:

- Các dòng hàng được cộng đúng và không tràn trước khi đi vào `VipPricing`.
- Đơn vị tiền đưa tới payment gateway đúng.
- Quy tắc ưu đãi thực tế của sản phẩm được mô tả đúng.
- API có kiểm tra quyền theo khách/tenant hay không.
- Hành vi dưới tải cao, lỗi DB hoặc thao tác đồng thời.
- Tất cả giá trị hợp lệ ngoài các trường hợp đã thử đều đúng.

Khi rủi ro nằm ở database, serialize, message broker hoặc gateway, cần **integration/contract tests**; khi rủi ro nằm ở hành trình nhiều thành phần, cần **E2E đại diện**. Công cụ test chỉ tạo bằng chứng cho **phạm vi test thực sự thực hiện**.

## 7. Coverage, mutation score và các con số dễ bị hiểu nhầm

**Code coverage** thường cho biết câu lệnh, dòng hoặc nhánh nào đã được thực thi. Nó giúp phát hiện vùng chưa được test chạm tới, nhưng không cho biết assertion có đúng hay trường hợp đầu vào có ý nghĩa hay không.

~~~java
@Test
void runsPricingButDoesNotAssert() {
    VipPricing.amountDueVnd(1_000_000L, true);
    // Có thể chạy qua logic nhưng không kiểm tra tiền trả về.
}
~~~

Test này có thể đóng góp coverage mà không phát hiện điều kiện ngưỡng sai.

**Mutation testing** tạo một số thay đổi giả định vào mã, chẳng hạn `>=` thành `>`, rồi xem bộ test có thất bại không. Nếu thay đổi sai sống sót, có thể tồn tại khoảng trống trong test. Nhưng mutation score không đo được mọi lỗi có thể xảy ra, và một mutation “sống sót” có thể tương đương về hành vi trong một ngữ cảnh nhất định.

### Chỉ số đo điều gì?

| Chỉ số | Câu hỏi hữu ích | Không được suy ra |
| --- | --- | --- |
| **Line coverage** | Dòng nào đã chạy trong bộ test? | 100% nghĩa là đúng trên mọi dữ liệu |
| **Branch coverage** | Những nhánh điều kiện nào đã được thực thi? | Mọi tổ hợp đầu vào, ngữ nghĩa và trạng thái đã đúng |
| **Mutation score** | Test có phát hiện các thay đổi nhân tạo trong tập mutation? | Không còn lỗi nào mà công cụ không tạo mutation |
| **Số test** | Có bao nhiêu kịch bản/đơn vị test đã đăng ký? | Nhiều test là bằng chứng mạnh hơn trong mọi trường hợp |
| **Số cảnh báo linter** | Còn bao nhiêu vi phạm theo ruleset? | Ít cảnh báo nghĩa là code an toàn hơn về mọi khía cạnh |
| **Thời gian pipeline** | Phản hồi đến nhanh và ổn định không? | Nhanh đồng nghĩa kiểm tra đủ rủi ro |
| **Tỷ lệ flaky** | Test có lặp lại ổn định không? | Mọi lỗi test đều do môi trường |
| **Kết quả quét phụ thuộc** | Có advisory/cảnh báo nào trong phạm vi được quét? | 0 cảnh báo nghĩa là thư viện không có lỗi chưa biết |

Cũng cần đọc **mẫu số**: coverage được tính trên file nào, có bỏ qua generated code, code mới hay code chưa instrument không? Số dòng không thể so trực tiếp giữa hai dự án có cấu trúc khác nhau. Các ngưỡng không nên khuyến khích thêm test vô nghĩa chỉ để đạt điểm.

## 8. Công cụ bảo mật: tìm dấu hiệu nguy cơ, không cấp chứng nhận an toàn

Bảo mật có nhiều loại rủi ro với bản chất khác nhau:

- **SAST (Static Application Security Testing):** tìm một số mẫu nguy cơ qua mã/luồng dữ liệu.
- **SCA (Software Composition Analysis):** phân tích thành phần và phiên bản phụ thuộc, đối chiếu danh sách rủi ro đã biết hoặc chính sách sử dụng thư viện.
- **Secret scanning:** tìm dấu hiệu khóa, token hoặc bí mật bị đưa vào mã, commit hoặc cấu hình theo pattern/heuristic.
- **DAST hoặc kiểm thử bảo mật động:** gửi các tương tác tới ứng dụng đang chạy trong phạm vi được phép để tìm những hành vi có nguy cơ.
- **Review chính sách và kiểm thử truy cập:** kiểm tra người dùng có quyền thực hiện hành động trên tài nguyên cụ thể hay không.

Những biện pháp này bổ sung nhau nhưng không thay thế nhau. Một SCA sạch không chứng minh phần code do đội viết không có lỗ hổng. Một SAST sạch không bảo đảm không có lỗi phân quyền theo đối tượng; một secret scanner sạch cũng không chứng minh secret không bị lộ qua log hoặc hệ thống ngoài repository.

### Trường hợp scanner khó suy ra chính sách nghiệp vụ

~~~java
Order loadOrder(long orderId) {
    return repository.findById(orderId).orElseThrow();
}
~~~

Không có gì trong đoạn mã tự chứng minh **người gọi có quyền đọc đơn ấy**. Tùy thiết kế, quyền có thể được kiểm ở tầng gọi, repository hoặc service. Scanner có thể không biết quy tắc sở hữu và tenant. Cần kiểm thử âm tính:

- Người dùng A đọc đơn của mình: cho phép.
- Người dùng B biết ID đơn của A: không nhận dữ liệu trái quyền.
- Nhân viên tenant X không tự đọc được tenant Y.
- API export, bulk và file download không đi vòng qua policy.

**“Không thấy cảnh báo” không thay thế một ma trận quyền với các trường hợp bị từ chối.**

### Rủi ro phụ thuộc cần được đánh giá theo ngữ cảnh

Một advisory khớp thư viện có thể cần phân loại:

1. Thành phần và phiên bản nào thực sự xuất hiện trong artifact được deploy?
2. Đường thực thi bị ảnh hưởng có tồn tại và có thể tiếp cận trong ứng dụng không?
3. Có bản vá hoặc biện pháp giảm thiểu nào đáng tin cậy?
4. Hậu quả nếu khai thác thành công là gì?
5. Khi nào sửa và cách kiểm tra không tạo hồi quy?

Không nên tự động coi mọi cảnh báo có cùng độ ưu tiên, nhưng cũng không dùng “đường code chắc không chạy” như lý do bỏ qua thiếu bằng chứng. **Điều tra rủi ro và quyết định có thời hạn** là phần của quy trình bảo mật.

## 9. Công cụ hiệu năng đo thứ được định nghĩa, không đo “nhanh” một cách tổng quát

JMH, profiler, load generator và metrics của ứng dụng trả lời các câu hỏi khác nhau:

| Công cụ/kiểu đo | Đọc đúng là gì? | Kết luận không hợp lệ |
| --- | --- | --- |
| **JMH microbenchmark** | Thời gian/throughput của một thao tác được định nghĩa với warmup, fork và dữ liệu cụ thể | API sẽ nhanh lên cùng tỷ lệ |
| **CPU/alloc profiler** | Phần code tiêu thụ CPU/cấp phát trong các mẫu được thu thập | Mọi thời gian chờ của request đều do hàm CPU “nóng” |
| **Load test** | Latency, throughput, lỗi và tài nguyên dưới workload thử | Production luôn đáp ứng mọi tải và dữ liệu |
| **Metrics và tracing** | Hành vi được instrument trên các ranh giới và khoảng đo | Tương quan giữa hai đồ thị đã chứng minh quan hệ nhân quả |

Giả sử JMH cho thấy một vòng lặp giảm từ 200 ns/op xuống 100 ns/op, nhưng API mất 200 ms vì chờ database. Đây có thể là tối ưu thật **ở cấp cục bộ** mà chưa tạo cải thiện đáng kể ở cấp ứng dụng. Cần dùng profiling/tracing để xác định tỷ trọng chi phí và đo lại dưới workload đại diện.

### Thế nào là tiêu chí hiệu năng có ý nghĩa?

Một tiêu chí ví dụ có thể là:

> “Trong môi trường thử với dữ liệu và cấu hình đã xác định, tại 150 yêu cầu/giây, p95 latency của endpoint không vượt 300 ms và tỷ lệ lỗi dưới 0,5%.”

Các số này **chỉ minh họa**. Để kiểm tra được, phải công bố điểm đo, phân bố request, thời lượng tải, điều kiện warmup, số request hoàn thành, cách tính timeout và môi trường.

Lỗi trả về nhanh có thể khiến latency trung bình trông tốt hơn, nên **tỷ lệ lỗi và kết quả nghiệp vụ** phải đi cùng số đo tốc độ. Không dùng một microbenchmark để thay bằng chứng về capacity, tail latency hoặc độ ổn định toàn hệ thống.

## 10. CI là hệ thống điều phối phép kiểm, không phải tiêu chí chất lượng

Một pipeline thường tự động chạy các bước khi có thay đổi mã:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Compile + unit test"]
    B --> C["Format + static checks"]
    C --> D["Integration / contract tests phù hợp"]
    D --> E["Security / dependency checks phù hợp"]
    E --> F{"Đạt policy đã cấu hình?"}
    F -->|"Không"| G["Chặn merge hoặc yêu cầu xử lý có lý do"]
    F -->|"Có"| H["Đủ điều kiện đi tới bước review / phát hành tiếp"]
    H --> I["Kiểm tra rủi ro còn lại và kế hoạch rollout"]
~~~

Sơ đồ chỉ minh họa thứ tự logic; các bước thực tế có thể chạy song song. Một pipeline **không tự biết** mình đang thiếu security test, API contract test hay rollback plan. Nó chỉ chạy các lệnh đã được cấu hình và báo theo trạng thái thực thi.

### Đọc đúng câu “CI xanh”

Nên hỏi:

- Commit nào, nhánh nào, môi trường nào đã được kiểm tra?
- Check nào được chạy thật? Có task bị skip, bị tắt hoặc không tìm thấy test không?
- Các dependency hoặc dịch vụ ngoài được mock hay dùng bản thử thực?
- Tại thời điểm nào? Kết quả quét phụ thuộc hôm trước có còn đủ mới không?
- Các giới hạn thời gian, dữ liệu, tenant, phiên bản consumer và hệ điều hành/JDK đã được bao phủ chưa?
- Có cảnh báo hoặc thất bại được miễn trừ không? Ai phê duyệt, đến khi nào?
- Có kiểm tra thủ công hoặc giám sát sau rollout nào được yêu cầu theo rủi ro?

**CI xanh nghĩa là pipeline hoàn thành theo điều kiện của nó tại một commit/môi trường cụ thể.** “Hệ thống đã đạt mọi tiêu chí chất lượng” là một khẳng định lớn hơn, cần nhiều bằng chứng hơn.

### Một ví dụ lệnh Java có phạm vi rõ

~~~bash
# Nếu dự án dùng Gradle với Java plugin và test đã cấu hình:
./gradlew test

# Task 'check' thường là điểm tích hợp kiểm tra của plugin;
# kiểm tra cụ thể chạy kèm tùy những plugin/rule dự án đã cấu hình:
./gradlew check
~~~

Không nên diễn giải `./gradlew check` là “đã chạy mọi static analyzer, quét bảo mật và E2E” khi những task ấy **chưa được nối vào build**. Mỗi dự án phải kiểm tra cấu hình và log thực tế của pipeline.

## 11. Quality gate: ngưỡng là quyết định quản trị rủi ro

Một **quality gate** là điều kiện quyết định có được đi tiếp hay không, ví dụ không có unit test thất bại, không vi phạm rule bảo mật nghiêm trọng mới hoặc không giảm coverage trên mã vừa thay đổi quá ngưỡng đã chọn.

Quality gate hữu ích vì chuyển những kỳ vọng đã thống nhất thành bước có thể lặp lại. Nhưng gate có thể trở thành mục tiêu sai nếu nhóm chỉ tìm cách đạt số.

### Hai tình huống đối lập

**Gate quá yếu:** CI chỉ kiểm tra format và compile, không kiểm tra hành vi tính tiền hoặc quyền truy cập. Pipeline luôn xanh kể cả khi lỗi nghiệp vụ đi qua.

**Gate quá cứng nhắc:** Bắt buộc mọi file đạt cùng một ngưỡng coverage rất cao; để vượt gate, nhóm tạo test chỉ gọi method, không assert hành vi quan trọng, hoặc bỏ qua file khó test. Số liệu đẹp lên nhưng rủi ro thực không giảm.

**Cách thiết kế tốt hơn:** bắt đầu từ rủi ro, chọn một số gate tự động có ý nghĩa, và kết hợp review/kiểm thử bổ sung cho những tiêu chí không thể lượng hóa bằng một con số.

| Tình huống | Gate hoặc biện pháp hợp lý | Điều kiện bổ sung |
| --- | --- | --- |
| Mã không biên dịch | Chặn ngay | Cần biết cấu hình JDK/build đang dùng |
| Test liên quan thất bại | Chặn và điều tra | Phân biệt lỗi sản phẩm với test/môi trường flaky |
| Secret khả nghi trong commit mới | Chặn hoặc xử lý khẩn theo policy | Xác minh, thu hồi/rotate khi là bí mật thật |
| Lỗ hổng phụ thuộc nghiêm trọng | Phân loại theo rủi ro, có hạn xử lý | Kiểm tra reachability, bản vá và giảm thiểu |
| Coverage code mới quá thấp | Tín hiệu cần review/test | Xem assertions và rủi ro, không “chạy cho đủ dòng” |
| p99 hồi quy ở workload đã định | Điều tra, có thể chặn theo SLO | Kiểm tra biến thiên của môi trường và tỷ lệ lỗi |
| Quy tắc style mới vi phạm do code cũ | Dùng baseline/triển khai dần | Không âm thầm bỏ quy tắc và không che vấn đề mới |

Ngưỡng và cách chặn cần có **chủ sở hữu**, giải thích lý do, giới hạn áp dụng và đường xử lý ngoại lệ. Không nên áp nguyên một “điểm chất lượng” tổng hợp vào mọi module khi bản chất và rủi ro khác nhau.

## 12. False positive, false negative và cách xử lý cảnh báo

Một đội triển khai công cụ mới thường gặp rất nhiều cảnh báo. Nếu mọi cảnh báo đều được coi là lỗi thật, nhóm sẽ tốn công vào nhiễu. Nếu mọi cảnh báo đều bị cho là “tool báo linh tinh”, rủi ro sẽ bị bỏ qua.

### Quy trình xử lý có kiểm soát

1. **Hiểu rule:** công cụ đang cảnh báo mẫu hành vi nào, trong phạm vi nào?
2. **Kiểm tra bằng chứng:** đường thực thi, dữ liệu, config, phiên bản và giả định liên quan.
3. **Đánh giá hậu quả:** nếu vi phạm là thật thì tác động tới bảo mật, đúng đắn, vận hành ra sao?
4. **Chọn hướng xử lý:** sửa mã, sửa cấu hình/rule, bổ sung test hoặc áp dụng ngoại lệ có giải thích.
5. **Ghi quyết định:** tại sao chấp nhận, ai chịu trách nhiệm và khi nào xem lại?
6. **Quan sát xu hướng:** cảnh báo mới so với baseline, tỉ lệ false positive, thời gian khắc phục.

### Ngoại lệ khác với im lặng tắt kiểm tra

Một số tình huống có thể chấp nhận suppression có phạm vi hẹp, nếu đã chứng minh rule không phù hợp:

~~~java
// Minh họa ý tưởng, KHÔNG phải annotation suppression dùng chung
// cho tất cả analyzer.
// Một công cụ cụ thể có thể có syntax suppress riêng;
// phải ghi lý do, rule và phạm vi theo quy ước dự án.
~~~

Không nên thêm `@SuppressWarnings("all")` trên toàn module chỉ để CI xanh. Một ngoại lệ tốt cần:

- **Phạm vi nhỏ:** một rule, một vị trí hoặc một đường thực thi rõ.
- **Lý do xác minh được:** vì sao kết luận này phù hợp với hệ thống.
- **Người chịu trách nhiệm và thời điểm xem lại:** nhất là cảnh báo rủi ro cao.
- **Biện pháp bổ sung:** test, kiểm soát vận hành hoặc thay đổi thiết kế nếu cần.

Nếu có thể, dùng baseline để phân biệt **nợ tồn tại** và **cảnh báo mới**, tránh chặn mọi thay đổi chỉ vì kho cũ đã có lỗi, đồng thời không cho phép thêm nợ mới không kiểm soát.

## 13. Thiết kế chiến lược kiểm tra dựa trên rủi ro thay vì danh sách công cụ

Giả sử một nhóm đang phát triển API checkout Java. Các rủi ro chính gồm tính giá sai, thanh toán trùng, lỗi quyền, sai contract JSON và độ trễ cao khi tải tăng.

Bảng sau chọn **bằng chứng cần có trước**, sau đó mới chọn công cụ:

| Rủi ro | Tiêu chí chấp nhận | Bằng chứng chủ lực | Điều phải xem thêm |
| --- | --- | --- | --- |
| VIP sai ở đúng ngưỡng | Tổng 1.000.000 VND được giảm theo chính sách | Unit test JUnit ở ranh giới | Xác nhận đặc tả và cách làm tròn |
| Số tiền gửi gateway khác giá đã tính | Hai giá trị theo cùng đơn vị, cùng chính sách | Component test với fake gateway, integration test adapter | Hợp đồng gateway thật, idempotency |
| Retry gây hai thanh toán | Một thao tác logic không tạo tác dụng phụ trùng không được phép | Integration/fault-injection, đối soát trạng thái | Timeout sau khi provider xử lý, đường rollback |
| Đọc đơn của tenant khác | Không trả dữ liệu ngoài quyền | API/DB authorization tests âm tính | Các route phụ, export, cache, background job |
| Client cũ không hiểu response | Hợp đồng công bố vẫn được đáp ứng trong giai đoạn hỗ trợ | Contract tests + serialization thực | Consumer còn chạy, phiên bản API |
| DB query tăng theo số bản ghi | Số query/request và p95 nằm trong mục tiêu | Metrics/tracing, integration/load test | Cache, heap, tỷ lệ lỗi, quyền |
| Lỗi do thư viện có advisory mới | Các phụ thuộc được quản lý theo risk policy | SCA, kiểm tra artifact deployed | Mức phơi nhiễm, bản vá, thời hạn |
| Code dễ đọc và dễ sửa | Tên và trách nhiệm rõ, biến không đổi nghĩa ngầm | Formatter/linter + human review | Không thể kết luận chỉ từ format |

Bảng thể hiện nguyên tắc: **“Mỗi loại bằng chứng trả lời một câu hỏi cụ thể.”** Không cần chạy E2E cho từng giá trị biên nếu unit test kiểm được tốt hơn, nhưng cũng không dùng unit test để thay kiểm tra giao tiếp với cổng thanh toán.

## 14. Chi phí phản hồi của công cụ cũng là một tiêu chí vận hành

Một bộ kiểm tra đúng nhưng quá chậm hoặc không ổn định có thể khiến đội ngũ bỏ qua cảnh báo hoặc không dám thay đổi mã. Cần đánh giá **giá trị tín hiệu trên chi phí phản hồi**:

- Thời gian chạy và thời gian chờ CI.
- Khả năng chẩn đoán khi thất bại.
- Số cảnh báo nhiễu và thời gian phân loại.
- Mức độ lặp lại ổn định giữa các máy/môi trường.
- Chi phí máy, tài nguyên và môi trường thử nghiệm.
- Công sức cập nhật rule, phiên bản tool và suppression.
- Thời điểm phát hiện lỗi: trên máy dev, trên PR, trước rollout hay sau phát hành.

Một cách phân tầng thường hữu ích:

~~~text
Trên máy phát triển:
  Format + compile + unit tests liên quan
            ↓
Pull request:
  Lint/static checks + unit tests + component/contract/integration phù hợp
            ↓
Trước phát hành hoặc theo lịch/rủi ro:
  E2E trọng yếu + security/performance/fault-injection phù hợp
            ↓
Sau rollout:
  Metrics/tracing + canary/smoke checks + xử lý sự cố và rollback
~~~

Đây chỉ là khung gợi ý. Một test E2E rất quan trọng, nhanh và ổn định có thể chạy trên mọi PR; quét phụ thuộc cũng có thể chạy thường xuyên. Phân tầng nên dựa vào **khả năng phát hiện rủi ro sớm** và năng lực của nhóm, không phải chia theo tên gọi cứng nhắc.

### Khi test flaky hoặc công cụ không ổn định

Đừng để “retry đến khi xanh” trở thành cơ chế chính. Cần kiểm tra dữ liệu dùng chung, race condition, timeout tùy tiện, nguồn thời gian, môi trường DB, phiên bản tool và sự khác biệt giữa cấu hình. Nếu tạm cách ly một test, phải ghi lại **khoảng trống bằng chứng** và hạn xử lý.

## 15. Một chương trình Java “không có cảnh báo” vẫn có thể khó bảo trì

Hãy so sánh hai cách tổ chức:

**Cách A:**

~~~java
long process(long x, boolean y, long z) {
    long a = x;
    if (y) {
        a = a * 90 / 100;
    }
    return a - z;
}
~~~

**Cách B (minh họa cấu trúc rõ hơn):**

~~~java
long calculateAmountDueVnd(
        long subtotalVnd,
        boolean vip,
        long couponDiscountVnd
) {
    long afterVipVnd = vip
            ? subtotalVnd - subtotalVnd / 10
            : subtotalVnd;

    return afterVipVnd - couponDiscountVnd;
}
~~~

Hai ví dụ có thể qua formatter/linter và có output giống nhau **trên một phần dữ liệu**, nhưng cần lưu ý:

- Phiên bản B nêu đơn vị và ý nghĩa các tham số rõ hơn.
- **Cả hai** vẫn cần validation: số âm, coupon lớn hơn số phải trả, giới hạn `long`.
- **Cả hai** vẫn cần xác định chính sách ngưỡng VIP; B chỉ kiểm tra cờ `vip`, chưa thể hiện ngưỡng.
- Phải xác nhận ý nghĩa công thức: `a * 90 / 100` và `a - a / 10` có thể **khác kết quả với một số giá trị không chia hết cho 10**, do phép chia số nguyên và thứ tự làm tròn.

Vì vậy, không nên coi “phiên bản B dễ đọc hơn” là lý do để thay A **mà không kiểm thử tương đương hành vi** hoặc xác nhận thay đổi nghiệp vụ. Đây là ví dụ về mối quan hệ giữa **readability**, **correctness** và khả năng giới hạn của kiểm tra tự động.

### Một lỗi khi biến chỉ số thành mục tiêu

Nếu tiêu chí đánh giá cá nhân là “không còn cảnh báo” hoặc “coverage 100%”, một số hành vi không mong muốn có thể xuất hiện:

- Xóa hoặc bỏ qua code khó kiểm tra thay vì hiểu rủi ro.
- Viết test chỉ để chạy qua dòng, không có kỳ vọng có ý nghĩa.
- Suppress nhiều cảnh báo mà không điều tra.
- Chia code vụn để đạt giới hạn số dòng mà làm rối luồng.
- Chọn cấu hình scanner ít báo để dashboard đẹp hơn.

**Chỉ số phải hỗ trợ quyết định**, không trở thành sự thay thế cho mục tiêu chất lượng thực. Khi thước đo thành mục tiêu duy nhất, việc tối ưu thước đo có thể làm giảm giá trị mà nó định đại diện.

## 16. Cách review một pull request có báo cáo công cụ

Một reviewer không cần tự chạy lại từng phép kiểm nếu CI đáng tin, nhưng cần đọc **phạm vi và tác động** của các thay đổi. Có thể hỏi:

1. **Thay đổi gì?** Logic nghiệp vụ, API, dữ liệu, quyền, dependency, cấu hình hay chỉ format?
2. **Rủi ro mới là gì?** Sai ngưỡng, sai owner/tenant, tràn số, retry trùng, rò rỉ tài nguyên?
3. **Tool nào đã chạy?** Những check nào thực sự được cấu hình, pass/skip/fail?
4. **Test nào bảo vệ hợp đồng mới?** Có trường hợp biên và trường hợp lỗi không?
5. **Có cảnh báo bị suppress hoặc gate được bỏ qua không?** Lý do và phạm vi là gì?
6. **Có thay đổi bên ngoài ranh giới unit test không?** Database, JSON, external service, event, permission?
7. **Các chỉ số có đại diện không?** Coverage và benchmark có cùng phạm vi với rủi ro đang xem xét?
8. **Có cần rollout/rollback hoặc monitoring riêng không?** Nhất là với dữ liệu và hợp đồng công khai.

### Ví dụ nhận xét review có ích

> “CI đã qua Checkstyle và unit tests. Tuy nhiên, thay đổi này chuyển điều kiện VIP từ `>=` sang `>`; các bài test hiện tại chỉ có giá trị cao hơn ngưỡng. Theo chính sách giảm từ 1.000.000 VND, cần bổ sung test đúng ngưỡng và kiểm tra số tiền gửi gateway. Khi đó kết quả CI mới cung cấp bằng chứng cho rủi ro của PR.”

Nhận xét này không phủ nhận giá trị tool. Nó chỉ ra **khoảng trống giữa điều được kiểm và điều cần bảo đảm**.

## 17. Checklist thiết kế hệ thống kiểm tra tự động

- [ ] Tôi có mô tả **mục tiêu chất lượng** trước khi chọn công cụ.
- [ ] Mỗi rule hoặc test quan trọng gắn được với rủi ro/hợp đồng cụ thể.
- [ ] Tôi biết phạm vi công cụ, phiên bản, cấu hình và file/module được quét.
- [ ] Tôi phân biệt lỗi được chứng minh với cảnh báo cần điều tra.
- [ ] Tôi không suy “linter xanh”, “coverage cao”, “scanner sạch” hoặc “CI xanh” thành không còn lỗi.
- [ ] Test có assertion đúng nghiệp vụ và bao phủ các trường hợp biên/hỏng quan trọng.
- [ ] Ranh giới DB, API, message broker hoặc payment gateway được kiểm tra khi rủi ro nằm ở đó.
- [ ] Kiểm tra bảo mật bao gồm quyền theo **đối tượng/tenant** chứ không chỉ token hợp lệ.
- [ ] Benchmark mô tả workload, đơn vị, điểm đo, latency/throughput/lỗi và môi trường.
- [ ] Quality gate có chủ sở hữu, ngưỡng hợp lý và đường xử lý ngoại lệ có lý do.
- [ ] Suppression có phạm vi, bằng chứng và thời điểm xem lại; không dùng bỏ qua toàn cục để che kết quả.
- [ ] CI thực sự chạy những bước được tuyên bố; task bị skip được nhận diện.
- [ ] Tôi cân bằng phản hồi nhanh với bằng chứng bổ sung cho rủi ro tích hợp lớn.
- [ ] Review và vận hành sau triển khai vẫn có vai trò đối với những điều kiểm tra tự động chưa thể chứng minh.

## 18. Những ngộ nhận thường gặp

**“Build xanh nghĩa là mã tốt.”** Build xanh chỉ cho biết các bước trong build đã hoàn thành theo điều kiện đã cấu hình.

**“Formatter làm code sạch.”** Formatter thống nhất hình thức; không quyết định chính sách nghiệp vụ, ranh giới bảo mật hoặc tính đúng đắn.

**“Static analyzer không báo gì nghĩa là không có bug.”** Công cụ chỉ xem được các pattern và mô hình mà nó hỗ trợ, dưới cấu hình đã chạy.

**“100% coverage nghĩa là mọi hành vi đã được kiểm tra.”** Coverage cho biết mã đã chạy, không bảo đảm assertions chính xác hoặc đủ kịch bản.

**“Càng nhiều test thì chất lượng chắc chắn càng cao.”** Một tập test trùng lặp, thiếu assertion và flaky có thể đem lại ít bằng chứng hơn vài test chọn đúng rủi ro.

**“Quét dependency sạch nghĩa là toàn bộ ứng dụng an toàn.”** SCA không kiểm soát hết lỗi do mã ứng dụng và cấu hình hoặc lỗ hổng chưa biết.

**“Mọi cảnh báo đều là bug thật.”** False positive tồn tại; cần điều tra theo rule và ngữ cảnh trước khi kết luận.

**“Một cảnh báo false positive cho phép tắt cả scanner.”** Ngoại lệ nên hẹp, có lý do và được xem lại; không làm mất các tín hiệu hữu ích khác.

**“Tối ưu cho điểm quality gate là tối ưu chất lượng.”** Nếu thước đo không khớp rủi ro, đạt điểm có thể tạo cảm giác an toàn giả.

**“Chạy thật nhiều E2E là tốt hơn unit test.”** Các cấp test bổ sung nhau; kiểm tra công thức ở cấp thấp thường nhanh và dễ chẩn đoán hơn.

**“Một benchmark cục bộ tốt là bằng chứng hệ thống chịu tải.”** JMH và load test có ranh giới khác nhau; cần đo lại ở mức ứng dụng.

**“Quy tắc do máy áp dụng thì khách quan tuyệt đối.”** Kết quả chạy rule có thể nhất quán, nhưng **lựa chọn rule, ngưỡng, phạm vi và điều kiện ngoại lệ** vẫn là quyết định của con người dựa trên rủi ro.

## 19. Bài tập thực hành

### Bài tập A — công cụ nào biết được điều gì?

Một PR thay:

~~~java
if (vip && totalVnd >= 1_000_000L) { ... }
~~~

thành:

~~~java
if (vip && totalVnd > 1_000_000L) { ... }
~~~

Formatter, compiler, static analysis và test hiện tại đều xanh. Hãy trả lời:

1. Lỗi nào có thể xuất hiện nếu yêu cầu là “từ 1.000.000 VND trở lên”?
2. Vì sao formatter/compiler không tự biết đây là lỗi?
3. Hãy viết tên và kỳ vọng của một JUnit test có khả năng phát hiện thay đổi này.
4. Khi nào nên bổ sung integration test ở ranh giới thanh toán?
5. Tiêu chí nào cần được đưa vào review checklist của nhóm?

### Bài tập B — đọc kết quả scanner

Một công cụ bảo mật phát hiện một thư viện có advisory. Một thành viên nói “cứ chặn mọi thứ”, thành viên khác nói “code của mình không dùng phần lỗi nên bỏ qua”. Hãy xây dựng quy trình phân loại gồm phiên bản được deploy, phạm vi ảnh hưởng, khả năng tiếp cận, biện pháp giảm thiểu, mức rủi ro, hạn sửa và bằng chứng để duy trì ngoại lệ nếu thực sự cần.

### Bài tập C — coverage cao nhưng thiếu bằng chứng

Module thanh toán có 95% line coverage, nhưng chỉ test happy path. Bạn sẽ chọn năm tình huống nào để tăng **giá trị bằng chứng**? Bắt buộc xét đầu vào biên, timeout, idempotency, quyền theo đối tượng và lỗi lưu dữ liệu.

### Bài tập D — thiết kế quality gate

Giả sử nhóm có pipeline 45 phút, thường flaky và 200 cảnh báo cũ. Hãy đề xuất:

- Check nào nên chạy sớm trên PR để có tín hiệu nhanh?
- Cách phân biệt cảnh báo mới và nợ cũ?
- Trường hợp nào được phép suppression và cần ghi điều gì?
- Test tích hợp nào phải giữ vì rủi ro cao?
- Cách đo xem quy trình cải tiến có giảm lỗi thật, thay vì chỉ giảm số cảnh báo?

### Bài tập E — xác minh một claim

Một dashboard ghi: “Quality score = A, không có vulnerability mới, coverage 90%, code smells = 0”. Bạn sẽ ghi thế nào trong báo cáo để phân biệt **điều đã kiểm**, **điều chưa biết** và **quyết định phát hành cần thêm bằng chứng**?

## 20. Câu hỏi tự kiểm tra

1. Tiêu chí chất lượng, quy tắc kiểm tra và công cụ khác nhau ở đâu? Lấy một ví dụ về tính đúng đắn.
2. Một Java formatter và một static analyzer hỗ trợ khả năng đọc bằng cách nào, và giới hạn của chúng là gì?
3. Vì sao mã compile được vẫn có thể vi phạm quyền truy cập hoặc tính sai tiền?
4. Một unit test xanh chứng minh điều gì? Điều gì nằm ngoài phạm vi của nó?
5. Vì sao branch/line coverage cao không đồng nghĩa nhiều hành vi quan trọng đã được xác minh?
6. Mutation testing giúp phát hiện loại khoảng trống nào và giới hạn của mutation score là gì?
7. Phân biệt SAST, SCA và kiểm thử authorization theo từng đối tượng.
8. Khi quét phụ thuộc báo nguy cơ nhưng không biết có được dùng tại runtime hay không, cần thu bằng chứng gì?
9. “CI xanh” cần kèm những thông tin nào để có thể diễn giải đáng tin?
10. Nếu check ở CI không hề được nối vào task chạy, có thể kết luận gì từ việc task `check` pass?
11. Một quality gate quá tập trung vào coverage có thể khuyến khích hành vi không mong muốn nào?
12. True positive, false positive và false negative khác nhau thế nào?
13. Vì sao suppression phải có lý do, phạm vi và thời gian xem lại?
14. Tại sao microbenchmark nhanh hơn chưa chứng minh latency API tốt hơn?
15. Khi nào test tích hợp quan trọng hơn unit test đối với lỗi database hoặc cổng thanh toán?
16. Nêu một ví dụ lỗi bảo mật do thiếu kiểm tra theo tenant mà linter không tự chứng minh được.
17. Làm thế nào để đánh giá chi phí phản hồi của một công cụ ngoài thời gian chạy?
18. Khi có chỉ số đẹp nhưng người dùng vẫn gặp lỗi, nhóm nên điều chỉnh **công cụ hay tiêu chí** theo trình tự nào?

## Ghi nhớ

**Công cụ kiểm tra tự động không phải định nghĩa của chất lượng mã nguồn.** Chất lượng bắt đầu từ những thuộc tính và hợp đồng cần được bảo vệ; công cụ là phương tiện thu bằng chứng có phạm vi và giới hạn. Hãy gắn từng check với rủi ro cụ thể, dùng formatter và phân tích tĩnh để giảm lỗi lặp lại, dùng test để xác minh hành vi, dùng scan và đo lường cho các ranh giới thích hợp, rồi kết hợp review và quan sát thực tế. Một pipeline tốt không chỉ “xanh” mà còn cho phép trả lời rõ **đã kiểm tra điều gì, chưa kiểm tra điều gì và vì sao bằng chứng hiện có đủ hoặc chưa đủ để ra quyết định**.
