# Kiểm thử hợp đồng API và các trường hợp lỗi

Kiểm thử hợp đồng API xác nhận một API thực hiện đúng những gì tài liệu công bố cho người gọi: đầu vào nào hợp lệ, kết quả nào được trả về, trạng thái nào được thay đổi và lỗi nào xuất hiện khi yêu cầu không hợp lệ. Hợp đồng cần ổn định ở ranh giới công khai, dù implementation bên trong được thay bằng bộ nhớ, database, HTTP adapter hoặc một phiên bản mới.

Một bộ kiểm thử tốt phải kiểm tra cả đường thành công lẫn đường lỗi. Đặc biệt, khi thao tác thất bại, API phải giữ đúng các bất biến đã cam kết: không ghi dữ liệu dở dang, không tạo side effect ngoài dự kiến, trả đúng loại lỗi hoặc mã lỗi và không làm lộ chi tiết nội bộ.

Bài học dùng Java 26 cùng JUnit Jupiter 6.1.3 để minh họa. JUnit là thư viện kiểm thử ổn định, không phải preview feature của Java. Các ví dụ tập trung vào hành vi quan sát được, kiểm thử tham số, tái sử dụng contract suite và cách xác minh lỗi ở API Java hoặc HTTP.

## 1. Hợp đồng API gồm những gì?

Một API contract là tập quy tắc mà caller có thể dựa vào khi tích hợp. Hợp đồng thường có các phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Input contract | Tham số nào bắt buộc, giới hạn và định dạng ra sao? | amount phải lớn hơn 0; accountId không được null |
| Output contract | Kết quả có cấu trúc và ý nghĩa gì? | transfer thành công trả receipt có mã giao dịch |
| Preconditions | Điều kiện nào phải đúng trước khi gọi? | Hai tài khoản tồn tại và khác nhau |
| Postconditions | Điều gì phải đúng sau khi gọi thành công? | Số dư nguồn giảm đúng amount, đích tăng đúng amount |
| Invariants | Điều gì luôn phải đúng trước và sau thao tác? | Tổng số dư không đổi khi chuyển tiền nội bộ |
| Error contract | Khi thất bại, loại lỗi và mã lỗi nào được công bố? | insufficient_funds, account_not_found |
| Side-effect contract | API được phép thay đổi những gì? | Không tạo giao dịch nếu validation thất bại |
| Compatibility contract | Caller cũ có tiếp tục hoạt động không? | Không đổi tên field JSON hoặc xóa method public |

Không cần biến mọi chi tiết implementation thành hợp đồng. Tên biến private, thứ tự gọi repository nội bộ hoặc cấu trúc class không công khai thường không phải điều caller được quyền dựa vào.

Một contract test nên thất bại khi API phá vỡ hành vi đã công bố, và vẫn pass khi implementation được tối ưu hoặc tái cấu trúc mà hành vi không đổi.

## 2. Phân biệt unit test, contract test và integration test

Ba loại kiểm thử bổ trợ nhau:

| Loại test | Phạm vi | Mục tiêu |
|---|---|---|
| Unit test | Một class hoặc một hàm | Kiểm tra logic nhỏ với fixture kiểm soát |
| API contract test | Ranh giới public của interface hoặc endpoint | Kiểm tra hành vi mà mọi caller/implementation phải tuân thủ |
| Integration test | Nhiều thành phần thật cùng hoạt động | Kiểm tra wiring, database, transaction, serialization, network và cấu hình |

Ví dụ, một implementation AccountLedger có thể dùng in-memory map, còn implementation khác dùng JDBC. Unit test riêng có thể kiểm tra cách từng class xử lý dữ liệu. Contract suite dùng chung xác nhận cả hai đều chuyển tiền chính xác, từ chối số tiền không hợp lệ và không làm thay đổi số dư khi giao dịch bị từ chối. Integration test với database thật kiểm tra transaction và constraint của hệ quản trị cơ sở dữ liệu.

Đừng gọi một test là contract test chỉ vì nó kiểm tra một method public. Điểm cốt lõi là test xác nhận quy tắc chung mà caller hoặc nhiều implementation phải tuân thủ.

## 3. Viết hợp đồng trước khi viết test

Hãy ghi rõ input, output, lỗi và side effect trước khi tạo test case. Ví dụ API chuyển tiền:

~~~java
public interface AccountLedger {
    BigDecimal balance(UUID accountId);

    void transfer(UUID sourceId, UUID targetId, BigDecimal amount);
}
~~~

Một hợp đồng mẫu cho transfer:

| Điều kiện | Kết quả được cam kết |
|---|---|
| sourceId hoặc targetId là null | Ném InvalidTransferException với code invalid_account |
| Hai ID giống nhau | Ném InvalidTransferException với code same_account |
| amount là null, bằng 0 hoặc âm | Ném InvalidTransferException với code invalid_amount |
| Tài khoản không tồn tại | Ném AccountNotFoundException |
| Số dư nguồn không đủ | Ném InsufficientFundsException |
| Transfer thành công | Số dư nguồn giảm amount, đích tăng amount |
| Bất kỳ lỗi từ chối nào | Không thay đổi số dư của cả hai tài khoản |
| Transfer thành công | Tổng số dư của hai tài khoản được giữ nguyên |

Đây là chính sách ví dụ của API. Trong hệ thống thực tế, nhóm phát triển cần thống nhất các quy tắc này trong tài liệu API, mã lỗi, schema và thỏa thuận với caller.

Hãy quyết định rõ những chi tiết sau:

- API có chấp nhận null không? Nếu không, lỗi là NullPointerException hay lỗi miền nghiệp vụ?
- API có phân biệt lỗi đầu vào với lỗi trạng thái nghiệp vụ không?
- Exception nào là public contract và exception nào chỉ là chi tiết nội bộ?
- Khi lỗi xảy ra, dữ liệu đã ghi trước đó có được rollback không?
- Retry cùng một yêu cầu có thể tạo side effect lặp lại không?
- Thứ tự kết quả, cách phân trang và quy tắc so sánh có ổn định không?

Không để test tự định nghĩa một hợp đồng khác với tài liệu API. Nếu test và tài liệu mâu thuẫn, hãy xác định đâu là hành vi được công bố và cập nhật bên còn lại có chủ đích.

## 4. Kiểm tra kết quả thành công và các invariant

Test thành công cần xác minh kết quả cuối cùng, không chỉ xác nhận method không ném exception.

Với transfer, các assertion cần bao phủ:

1. Số dư nguồn giảm đúng số tiền.
2. Số dư đích tăng đúng số tiền.
3. Tổng số dư không đổi.
4. Không có tài khoản thứ ba bị thay đổi.
5. Nếu API trả receipt, receipt có định danh và dữ liệu đúng hợp đồng.

Ví dụ dùng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;

abstract class AccountLedgerTest {
    protected abstract AccountLedger createLedger();

    protected abstract void openAccount(
        AccountLedger ledger, UUID id, BigDecimal openingBalance);

    @Test
    void transferMovesExactlyTheRequestedAmount() {
        AccountLedger ledger = createLedger();
        UUID source = UUID.randomUUID();
        UUID target = UUID.randomUUID();

        openAccount(ledger, source, new BigDecimal("100.00"));
        openAccount(ledger, target, new BigDecimal("25.00"));

        ledger.transfer(source, target, new BigDecimal("30.00"));

        assertAll(
            () -> assertMoneyEquals(
                new BigDecimal("70.00"), ledger.balance(source)),
            () -> assertMoneyEquals(
                new BigDecimal("55.00"), ledger.balance(target))
        );
    }

    private static void assertMoneyEquals(
            BigDecimal expected, BigDecimal actual) {
        assertEquals(0, expected.compareTo(actual),
            () -> "Expected " + expected + " but was " + actual);
    }

}
~~~

Trong ví dụ này, createLedger và openAccount là điểm nối fixture để minh họa. Test thực tế cần thay chúng bằng fixture của implementation đang kiểm tra.

Dùng BigDecimal.compareTo khi hợp đồng chỉ quan tâm giá trị tiền. BigDecimal.equals còn so sánh scale, vì vậy 30.0 và 30.00 không bằng nhau theo equals dù chúng biểu diễn cùng giá trị số. Nếu scale là một phần của hợp đồng dữ liệu, hãy kiểm tra scale riêng.

assertAll giúp chạy tất cả assertion trong nhóm và báo nhiều sai lệch cùng lúc. Dùng nó cho các hậu điều kiện độc lập; không gom những assertion phụ thuộc vào một giá trị chưa được kiểm tra an toàn.

## 5. Kiểm tra exception đúng hợp đồng

Một test lỗi không nên chỉ xác nhận “có exception”. Hãy xác minh:

- Loại exception được công bố.
- Mã lỗi ổn định nếu API có mã lỗi.
- Trạng thái dữ liệu sau lỗi.
- Không có side effect ngoài hợp đồng.
- Thông tin lỗi không tiết lộ secret, SQL, stack trace hoặc chi tiết nội bộ.

Ví dụ:

Giả sử test fixture đã tạo ledger cùng hai tài khoản có số dư ban đầu; đoạn dưới đây tập trung vào phần gọi API và kiểm tra hợp đồng lỗi.

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void insufficientFundsDoesNotChangeEitherBalance() {
    UUID source = UUID.randomUUID();
    UUID target = UUID.randomUUID();

    openAccount(ledger, source, new BigDecimal("10.00"));
    openAccount(ledger, target, new BigDecimal("5.00"));

    InsufficientFundsException error = assertThrows(
        InsufficientFundsException.class,
        () -> ledger.transfer(
            source, target, new BigDecimal("20.00"))
    );

    assertAll(
        () -> assertEquals("insufficient_funds", error.code()),
        () -> assertMoneyEquals(
            new BigDecimal("10.00"), ledger.balance(source)),
        () -> assertMoneyEquals(
            new BigDecimal("5.00"), ledger.balance(target))
    );
}
~~~

assertThrows trả về exception để kiểm tra thêm mã lỗi hoặc thuộc tính public. Nó chấp nhận exception thuộc lớp chỉ định hoặc lớp con. Nếu hợp đồng bắt buộc chính xác một loại exception và không cho subclass, dùng assertThrowsExactly.

Không khóa test vào toàn bộ message nếu message không phải nội dung API cam kết. Message có thể được biên tập lại để rõ hơn hoặc dịch sang ngôn ngữ khác. Mã lỗi như invalid_amount hoặc insufficient_funds thường phù hợp hơn cho client xử lý.

### 5.1. Exception kiểm tra và exception không kiểm tra

Hợp đồng cần mô tả rõ exception có thể xuất hiện. Checked exception buộc caller xử lý hoặc khai báo trong throws; unchecked exception không tạo ràng buộc compile-time tương tự.

Không thay đổi tùy tiện từ checked sang unchecked hoặc ngược lại nếu public API đã công bố loại lỗi cụ thể. Việc đổi có thể ảnh hưởng mã caller, dù tên method và kiểu trả về vẫn giữ nguyên.

Cũng không bắt Throwable để biến mọi lỗi thành một response nghiệp vụ chung. OutOfMemoryError, linkage error và các lỗi nghiêm trọng của JVM không phải lỗi đầu vào bình thường mà API nên che giấu.

## 6. Dùng parameterized test cho ma trận đầu vào

Nhiều lỗi có cùng quy tắc nhưng khác giá trị đầu vào. Parameterized test giúp chạy một test logic với nhiều trường hợp, đồng thời báo rõ bộ dữ liệu nào thất bại.

Ví dụ kiểm tra amount:

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.math.BigDecimal;
import java.util.UUID;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class TransferValidationContractTest {
    @ParameterizedTest
    @MethodSource("invalidAmounts")
    void rejectsInvalidAmountWithoutChangingBalances(
            BigDecimal amount, String expectedCode) {

        AccountLedger ledger = createLedgerWithTwoAccounts();
        UUID source = sourceId();
        UUID target = targetId();

        BigDecimal sourceBefore = ledger.balance(source);
        BigDecimal targetBefore = ledger.balance(target);

        InvalidTransferException error = assertThrows(
            InvalidTransferException.class,
            () -> ledger.transfer(source, target, amount)
        );

        assertAll(
            () -> assertEquals(expectedCode, error.code()),
            () -> assertMoneyEquals(
                sourceBefore, ledger.balance(source)),
            () -> assertMoneyEquals(
                targetBefore, ledger.balance(target))
        );
    }

    static Stream<Arguments> invalidAmounts() {
        return Stream.of(
            arguments(null, "invalid_amount"),
            arguments(BigDecimal.ZERO, "invalid_amount"),
            arguments(new BigDecimal("-0.01"), "invalid_amount")
        );
    }

    // Các helper fixture được triển khai trong test adapter.
}
~~~

Ma trận đầu vào nên tập trung vào các nhóm có ý nghĩa với hợp đồng:

| Nhóm | Giá trị nên kiểm tra |
|---|---|
| Nullability | null ở từng tham số được phép hoặc bị từ chối |
| Empty | Chuỗi rỗng, collection rỗng, payload không có phần tử |
| Whitespace | Chuỗi chỉ có khoảng trắng, tab, newline |
| Numeric boundary | 0, số âm, giá trị tối thiểu/tối đa, sát ngưỡng |
| Precision | Scale, rounding, overflow và giá trị vượt precision |
| Text | Unicode, ký tự tổ hợp, độ dài tối đa, ký tự điều khiển |
| Time | Ngày nhuận, cuối tháng, offset, daylight-saving transition |
| Collection | Trùng phần tử, thứ tự, collection rất lớn |
| Pagination | Page size bằng 0, âm, quá giới hạn, trang cuối và trang rỗng |

Không cần kiểm tra mọi tổ hợp của mọi trường. Chọn các trường hợp đại diện cho từng quy tắc và các cặp có tương tác. Với dữ liệu biên, thêm trường hợp ngay dưới, đúng bằng và ngay trên giới hạn.

## 7. Kiểm tra null, định dạng và lỗi xác thực

Nếu API từ chối null, test phải xác minh hành vi được tài liệu hóa. Đừng mặc định mọi API đều nên ném NullPointerException; API miền nghiệp vụ có thể định nghĩa InvalidRequestException hoặc trả validation result.

Ví dụ:

Đoạn test sau dùng fixture tạo sẵn hai tài khoản và các helper trả về ID tương ứng.

~~~java
@Test
void nullAccountIdIsRejectedBeforeAnyMutation() {
    AccountLedger ledger = createLedgerWithTwoAccounts();

    BigDecimal sourceBefore = ledger.balance(sourceId());
    BigDecimal targetBefore = ledger.balance(targetId());

    InvalidTransferException error = assertThrows(
        InvalidTransferException.class,
        () -> ledger.transfer(null, targetId(), new BigDecimal("1.00"))
    );

    assertAll(
        () -> assertEquals("invalid_account", error.code()),
        () -> assertMoneyEquals(sourceBefore, ledger.balance(sourceId())),
        () -> assertMoneyEquals(targetBefore, ledger.balance(targetId()))
    );
}
~~~

Nếu API có chuẩn hóa dữ liệu, test cả hai mặt:

- Giá trị được chấp nhận có được chuẩn hóa đúng không?
- Giá trị không hợp lệ có bị từ chối nhất quán không?
- Dữ liệu gốc có bị thay đổi ngoài ý muốn không?
- Hai biểu diễn tương đương có được xử lý như nhau theo hợp đồng không?

Không kiểm tra implementation nội bộ bằng reflection để xác nhận một biến private chứa giá trị đã trim. Hãy gọi API công khai và quan sát kết quả trả về hoặc side effect đã cam kết.

## 8. Kiểm tra lỗi mà không tạo side effect dở dang

Một trong những lỗi nghiêm trọng nhất là thao tác thất bại sau khi đã ghi một phần dữ liệu.

Với thao tác nhiều bước, hợp đồng cần xác định tính atomicity: hoặc toàn bộ thao tác thành công, hoặc không có thay đổi nghiệp vụ nào được lưu.

Ví dụ transfer có thể gồm:

1. Kiểm tra hai tài khoản.
2. Kiểm tra số dư.
3. Ghi giảm tài khoản nguồn.
4. Ghi tăng tài khoản đích.
5. Ghi lịch sử giao dịch.

Nếu bước 4 hoặc 5 thất bại, database transaction phải rollback những thay đổi trước đó theo hợp đồng. Test integration nên cố ý tạo lỗi tại một bước sau khi đã có thay đổi để xác nhận rollback thực sự.

| Điểm lỗi giả lập | Kết quả cần xác minh |
|---|---|
| Validation thất bại trước khi ghi | Không có row hoặc event mới |
| Ghi giảm nguồn thành công, ghi tăng đích thất bại | Số dư nguồn được khôi phục |
| Ghi số dư thành công, ghi audit thất bại | Kết quả theo đúng chính sách atomicity đã công bố |
| Timeout trước khi biết kết quả commit | API có quy tắc truy vấn trạng thái hoặc idempotency rõ ràng |
| Retry cùng request | Không tạo giao dịch trùng nếu API cam kết idempotency |

Không giả lập lỗi bằng cách sửa private field của service. Dùng test seam ở ranh giới phụ thuộc, database constraint, transaction hook hoặc adapter có thể điều khiển được. Với transaction và locking, phải có integration test trên database thật hoặc môi trường tương đương; mock repository không chứng minh database rollback đúng.

## 9. Kiểm thử hợp đồng dùng chung cho nhiều implementation

Khi nhiều implementation cùng thực hiện một interface, nên viết một contract suite dùng lại. Mỗi implementation chỉ cung cấp fixture và cách tạo dữ liệu ban đầu; các quy tắc chung được định nghĩa một lần.

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;

abstract class AccountLedgerContractTest {
    protected abstract AccountLedger newLedger();

    protected abstract void openAccount(
        AccountLedger ledger, UUID id, BigDecimal openingBalance);

    private static void assertMoneyEquals(
            BigDecimal expected, BigDecimal actual) {
        assertEquals(0, expected.compareTo(actual));
    }

    @Test
    void transferMovesFundsAndPreservesTotal() {
        AccountLedger ledger = newLedger();
        UUID source = UUID.randomUUID();
        UUID target = UUID.randomUUID();

        openAccount(ledger, source, new BigDecimal("100.00"));
        openAccount(ledger, target, new BigDecimal("20.00"));

        ledger.transfer(source, target, new BigDecimal("40.00"));

        assertAll(
            () -> assertMoneyEquals(
                new BigDecimal("60.00"), ledger.balance(source)),
            () -> assertMoneyEquals(
                new BigDecimal("60.00"), ledger.balance(target))
        );
    }

    @Test
    void rejectedTransferDoesNotChangeBalances() {
        AccountLedger ledger = newLedger();
        UUID source = UUID.randomUUID();
        UUID target = UUID.randomUUID();

        openAccount(ledger, source, new BigDecimal("10.00"));
        openAccount(ledger, target, new BigDecimal("20.00"));

        assertThrows(
            InsufficientFundsException.class,
            () -> ledger.transfer(
                source, target, new BigDecimal("50.00"))
        );

        assertAll(
            () -> assertMoneyEquals(
                new BigDecimal("10.00"), ledger.balance(source)),
            () -> assertMoneyEquals(
                new BigDecimal("20.00"), ledger.balance(target))
        );
    }
}
~~~

Một lớp test cụ thể cho in-memory ledger và một lớp test cụ thể cho JDBC ledger có thể kế thừa contract suite này. JUnit Jupiter chạy các test method kế thừa từ lớp cha trên lớp test cụ thể.

Lưu ý khi tái sử dụng contract suite:

- Mỗi test cần fixture mới hoặc dữ liệu được reset đáng tin cậy.
- Test database phải cô lập dữ liệu theo test run, không dựa vào thứ tự chạy.
- Không dùng chung account ID cố định giữa các test chạy song song.
- Test adapter phải cung cấp đúng setup/cleanup mà implementation cần.
- Nếu một implementation có giới hạn khác, xác định đó có phải khác biệt hợp đồng hay chỉ là khác biệt nội bộ.

Không nới lỏng contract suite để che một implementation sai. Nếu một implementation không đáp ứng hợp đồng, sửa implementation hoặc thay đổi hợp đồng công khai có chủ đích và cập nhật tất cả caller.

## 10. Kiểm thử hợp đồng của HTTP API

Với REST API, contract thường gồm HTTP method, path, request schema, response schema, status code, header và quy tắc lỗi. Test cần xác minh response thực tế phù hợp với tài liệu OpenAPI hoặc schema đã công bố.

| Thành phần HTTP | Điều cần kiểm tra |
|---|---|
| Method và path | Endpoint đúng method, path và version |
| Request | Required fields, kiểu dữ liệu, giới hạn và định dạng |
| Success status | Status code theo từng thao tác, ví dụ 200, 201 hoặc 204 |
| Error status | Status cho validation, not found, conflict hoặc lỗi server theo hợp đồng |
| Content-Type | Media type và charset phù hợp |
| Response body | Field bắt buộc, kiểu dữ liệu, nullability và enum |
| Headers | Location, ETag, Retry-After, request ID hoặc pagination links nếu được công bố |
| Pagination | Quy tắc page token, sort order, page size và trang cuối |
| Idempotency | Retry cùng idempotency key có hành vi được xác định |
| Compatibility | Client cũ vẫn hiểu response và error schema mới |

Ví dụ nếu API sử dụng Problem Details theo RFC 9457, test có thể xác minh media type và mã lỗi mở rộng:

~~~java
assertEquals(422, response.statusCode());
assertEquals(
    "application/problem+json",
    response.headers().firstValue("Content-Type").orElseThrow()
);
assertEquals("invalid_amount", problem.code());
~~~

Status 422 chỉ đúng nếu API contract chọn status đó cho lỗi này. Một API khác có thể quy định 400. Không áp đặt mã status tùy ý từ test; test phải theo hợp đồng được công bố.

Nếu response có error message cho người dùng, test nội dung message chỉ khi câu chữ là một phần hợp đồng. Với machine client, thường nên ưu tiên mã lỗi ổn định và field có cấu trúc. Không để response 5xx chứa SQL query, stack trace, file path, token hoặc thông tin hệ thống nội bộ.

### 10.1. Contract giữa consumer và provider

Trong hệ thống có nhiều service, consumer và provider cần thống nhất:

- Consumer chỉ gửi field và giá trị được provider hỗ trợ.
- Provider giữ tương thích với field mà consumer đang sử dụng.
- Field mới có quy tắc default rõ ràng.
- Field bị loại bỏ phải có giai đoạn deprecation và lịch ngừng hỗ trợ.
- Enum mới không làm client cũ lỗi nếu client được yêu cầu xử lý giá trị chưa biết.
- Thay đổi status code hoặc error schema phải được xem là thay đổi contract.

Có thể kiểm tra schema OpenAPI ở phía provider và chạy bộ test consumer trên response thật hoặc response được ghi lại. Nếu dùng consumer-driven contract tooling, cần kiểm tra trạng thái hỗ trợ, phiên bản và quy tắc quản lý contract của công cụ đó trước khi đưa vào pipeline. Tài liệu schema vẫn là nguồn hợp đồng chính thức.

## 11. Kiểm thử thứ tự, phân trang và tính idempotent

API trả collection thường có nhiều quy tắc dễ bị bỏ sót:

- Thứ tự mặc định có ổn định hay không?
- Khi hai bản ghi có cùng sort key, có tie-breaker không?
- Trang cuối trả danh sách rỗng hay lỗi?
- Page size vượt giới hạn bị từ chối hay được giới hạn về maximum?
- Token phân trang có dùng được sau khi dữ liệu thay đổi không?
- Kết quả trùng lặp có được phép không?

Nếu API cam kết sort theo thời gian và ID, test phải xác minh cả hai khóa. Không chỉ kiểm tra danh sách có đúng các phần tử mà bỏ qua thứ tự.

Với thao tác tạo đơn hàng, thanh toán hoặc transfer, hãy kiểm tra idempotency nếu hợp đồng có cam kết. Cùng một idempotency key và cùng payload thường phải trả lại cùng kết quả nghiệp vụ hoặc cùng resource đã tạo, không tạo side effect lần thứ hai. Cùng key nhưng payload khác cần có hành vi lỗi được xác định.

Không mặc định mọi POST đều idempotent. Hãy ghi rõ quy tắc retry ở API contract.

## 12. Kiểm thử concurrency khi API cam kết an toàn đồng thời

Nếu API cho phép nhiều thread hoặc request cập nhật cùng một tài nguyên, hợp đồng có thể bao gồm tính nhất quán khi thao tác đồng thời.

Các tình huống nên kiểm tra:

- Hai transfer cùng đọc một số dư trước khi cập nhật.
- Hai request cập nhật cùng version hoặc ETag.
- Hai request cùng idempotency key đến gần như đồng thời.
- Nhiều request cùng ghi một bản ghi duy nhất.
- Retry xảy ra khi request đầu chưa rõ đã commit hay chưa.

Test concurrency phải dùng latch, barrier hoặc cơ chế đồng bộ có kiểm soát. Không dùng Thread.sleep để hy vọng hai thread chạy đúng thời điểm. Kiểm tra hậu điều kiện sau khi tất cả task kết thúc và thu thập mọi exception từ Future.

Không chạy test đồng thời trên cùng một fixture mutable nếu test không được thiết kế cho việc chia sẻ. Nếu API không cam kết thứ tự hoặc tính đồng thời cụ thể, đừng biến một quan sát tình cờ của implementation thành contract.

## 13. Kiểm thử thời gian, môi trường và dữ liệu không xác định

Một contract test nên tái lập được. Những yếu tố như đồng hồ hệ thống, timezone mặc định, locale, random, file system và network có thể làm test chập chờn.

| Yếu tố | Cách kiểm soát |
|---|---|
| Thời gian hiện tại | Inject Clock và dùng Clock.fixed trong unit/contract test |
| Timezone | Truyền ZoneId rõ ràng; không phụ thuộc timezone máy chạy |
| Locale | Dùng Locale cụ thể khi định dạng/parsing |
| Random | Inject seed hoặc nguồn random xác định trong test |
| File system | Dùng thư mục tạm riêng cho từng test |
| Network | Dùng server thử nghiệm hoặc adapter kiểm soát được |
| Environment variable | Đặt/khôi phục giá trị trong phạm vi test |
| System property | Lưu giá trị cũ và khôi phục sau test |

Không đặt test phụ thuộc vào thời điểm chạy như “phải hoàn tất dưới 20 ms” trong unit suite thông thường. Hiệu năng cần benchmark hoặc performance test với môi trường được kiểm soát. Unit test có thể dùng timeout để phát hiện treo, nhưng timeout không phải cam kết latency production.

Nếu test sử dụng JUnit parallel execution, không sửa system property hoặc timezone mặc định toàn cục trong nhiều test cùng lúc trừ khi dùng cơ chế resource lock phù hợp. JUnit 6 có hỗ trợ các extension quản lý môi trường như default locale/timezone và system properties; vẫn phải thiết kế test độc lập và khôi phục trạng thái.

## 14. Không kiểm thử implementation detail

Một test quá gắn với cách triển khai có thể thất bại dù API vẫn đúng. Ví dụ:

- Xác minh private field bằng reflection.
- Bắt buộc một method nội bộ phải được gọi đúng số lần.
- Kiểm tra SQL string nội bộ thay vì kết quả và transaction behavior.
- Bắt buộc implementation phải dùng một class cụ thể.
- Dựa vào thứ tự iteration của HashMap khi hợp đồng không cam kết.
- Kiểm tra log debug nội bộ như thể đó là response API.

Hãy test qua public interface, public endpoint, database state hoặc event đã được công bố. Có thể dùng spy/mock để kiểm tra tương tác khi interaction là một phần hợp đồng, ví dụ không gọi payment provider khi validation thất bại. Nhưng nếu chỉ quan tâm trạng thái cuối, ưu tiên assertion vào trạng thái đó.

## 15. JUnit 6.1.3 trên JDK 26

Tại thời điểm JDK 26 được sử dụng trong module này, JUnit 6.1.3 là bản GA hiện hành được tài liệu JUnit công bố. JUnit 6 yêu cầu Java 17 trở lên ở runtime nên có thể chạy trên JDK 26.

Ví dụ Maven dependency:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.version}</version>
    <scope>test</scope>
</dependency>
~~~

Nếu biên dịch mã nguồn bằng JDK 26 và mục tiêu phát hành là Java 26, đặt release target:

~~~xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <junit.version>6.1.3</junit.version>
</properties>
~~~

Với Maven Surefire/Failsafe hỗ trợ JUnit Platform, chạy test bằng lệnh build thông thường:

~~~sh
mvn test
~~~

Dùng phiên bản Maven Surefire/Failsafe có hỗ trợ JUnit Platform để chạy test; kiểm tra build tool và IDE đang dùng cùng JDK dự kiến. Dependency JUnit không tự bảo đảm compiler hoặc test runner đã chạy bằng JDK 26.

Phân biệt các thành phần JUnit:

| Thành phần | Vai trò | Trạng thái sử dụng |
|---|---|---|
| JUnit Platform | Nền tảng khám phá và chạy test engine | Thành phần nền tảng hiện hành |
| JUnit Jupiter | API viết test và engine cho test hiện đại | Lựa chọn chính cho test mới |
| JUnit Vintage | Chạy test JUnit 3/4 trên Platform | Deprecated; chỉ giữ tạm trong giai đoạn migration |

JUnit 6.2.0-M1 là milestone/pre-release, không nên dùng làm baseline production nếu mục tiêu là dependency GA ổn định. JUnit 6 không cần bật Java preview. Các annotation như @Test, @ParameterizedTest và assertion API là API thư viện, không phải tính năng preview của JDK.

Nếu code được kiểm thử sử dụng preview language feature của JDK 26, việc biên dịch và chạy test phải bật preview theo đúng JDK 26. Preview feature gắn với release cụ thể; không giả định bytecode preview của JDK 26 có thể chạy như API ổn định trên JDK khác. Giữ preview code trong phạm vi thử nghiệm và đánh giá lại khi nâng JDK.

## 16. Chạy test trên nhiều JDK và nhiều môi trường

Nếu thư viện công bố hỗ trợ nhiều JDK, compile và test theo từng release mà thư viện cam kết. Với API sử dụng tính năng Java 26, ít nhất cần một job compile/test trên JDK 26. Nếu code phải chạy trên release thấp hơn, hãy biên dịch với --release tương ứng và tránh gọi API chỉ có ở JDK 26.

Một ma trận CI đơn giản:

| Job | JDK | Mục tiêu |
|---|---|---|
| Compile Java 26 | JDK 26 | Xác nhận source và API target biên dịch |
| Unit/contract tests | JDK 26 | Xác nhận hành vi API trên runtime mục tiêu |
| Integration tests | JDK 26 + database/service thử nghiệm | Xác nhận transaction, serialization và wiring |
| Compatibility tests | Các JDK nằm trong support matrix | Xác nhận hành vi trên các runtime được công bố |
| API schema check | Schema version đã phát hành | Phát hiện breaking change trong HTTP/event contract |

Không chạy test trên một JDK duy nhất rồi kết luận mọi runtime được hỗ trợ đều tương thích. Ngược lại, cũng không cần chạy mọi test trên mọi JDK nếu sản phẩm chỉ hỗ trợ một runtime; ma trận phải phản ánh cam kết thực tế.

## 17. Tổ chức test suite để chẩn đoán lỗi nhanh

Tách test theo phạm vi và thời gian chạy:

- Unit tests: chạy thường xuyên, không cần network hoặc database ngoài.
- Contract tests: chạy trên từng implementation hoặc adapter để xác nhận cùng một hành vi.
- Integration tests: kiểm tra database, message broker, HTTP serialization và transaction.
- End-to-end tests: xác nhận các luồng quan trọng qua nhiều service.
- Compatibility tests: so sánh schema/API với phiên bản đã phát hành.

Tên test nên mô tả điều kiện và kết quả, ví dụ transferRejectsNonPositiveAmount hoặc duplicateIdempotencyKeyReturnsOriginalResult. Tránh tên chung như test1 hoặc testError.

Khi test lỗi, failure message cần chỉ rõ input, expected contract và actual result nhưng không ghi dữ liệu nhạy cảm. Không log token, password, private key hoặc payload có dữ liệu cá nhân thật.

## 18. Quy trình xây dựng contract suite

1. Đọc tài liệu public API, OpenAPI/schema và error catalog.
2. Viết bảng precondition, postcondition, invariant và lỗi.
3. Chọn một luồng thành công đại diện và xác minh toàn bộ hậu điều kiện.
4. Liệt kê input invalid, boundary và state conflict.
5. Với mỗi lỗi, xác minh exception/status, error code và trạng thái sau lỗi.
6. Tạo parameterized tests cho các nhóm input cùng quy tắc.
7. Đóng gói contract suite để chạy trên mọi implementation.
8. Bổ sung integration test cho transaction, persistence, HTTP và concurrency.
9. Chạy compile/test trên JDK thuộc support matrix.
10. Đưa schema/API compatibility check vào pipeline trước khi phát hành.

Một contract suite chỉ có giá trị khi các test phản ánh quy tắc đã được caller chấp nhận. Khi thay đổi contract, hãy cập nhật tài liệu, test, client và versioning policy cùng nhau.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ test đường thành công | Lỗi validation và trạng thái lỗi không được phát hiện | Viết error matrix cho từng API operation |
| Chỉ assert exception có xuất hiện | Có thể nhận sai loại lỗi hoặc sai code | Kiểm tra type, code và hậu điều kiện |
| Không kiểm tra state sau lỗi | Giao dịch có thể ghi dở dang | Xác minh invariant và atomicity |
| Khóa test vào message đầy đủ | Message đổi làm test hỏng dù contract không đổi | Ưu tiên error code và field công khai |
| Chỉ test một implementation | Adapter khác có thể vi phạm cùng interface | Tái sử dụng contract suite |
| Dùng mock để kết luận transaction đúng | Không xác nhận rollback của database thật | Bổ sung integration test với database |
| Dùng Thread.sleep cho concurrency | Test chập chờn theo tải máy | Dùng latch, barrier và Future |
| Test dựa vào thứ tự collection không cam kết | Test lỗi ngẫu nhiên hoặc khóa implementation | Công bố sort order hoặc không assert order |
| Dùng dữ liệu production trong test | Rủi ro riêng tư và khó tái lập | Dùng dữ liệu giả lập/anonymized |
| Chạy JUnit milestone trong production baseline | Có thể gặp API và behavior chưa ổn định | Dùng JUnit GA phù hợp |
| Giữ JUnit Vintage lâu dài | Duy trì engine migration đã deprecated | Chuyển test sang Jupiter rồi loại Vintage |
| Dùng --enable-preview cho test không cần thiết | Tăng phụ thuộc vào JDK release | Chỉ bật preview khi test thực sự sử dụng preview API |
| Bỏ qua compile target | Test chạy trên JDK mới nhưng artifact dùng API ngoài target | Cấu hình --release và test trên runtime mục tiêu |

## 20. Checklist kiểm thử hợp đồng API

- [ ] Hợp đồng input/output được mô tả rõ và có version.
- [ ] Preconditions, postconditions và invariants được ghi thành quy tắc có thể kiểm tra.
- [ ] Error type/status và machine-readable error code được xác định.
- [ ] Test đường thành công xác minh toàn bộ hậu điều kiện.
- [ ] Test null, empty, malformed, boundary và giá trị vượt giới hạn.
- [ ] Test lỗi xác minh trạng thái dữ liệu không thay đổi ngoài hợp đồng.
- [ ] Test exception không phụ thuộc message nội bộ nếu message không public.
- [ ] Test idempotency, pagination, ordering và concurrency khi API cam kết.
- [ ] Contract suite được chạy trên mọi implementation/adapter.
- [ ] Integration test kiểm tra transaction, database và HTTP behavior thật.
- [ ] HTTP test xác minh status, header, schema và error body.
- [ ] Test độc lập, deterministic, không phụ thuộc thứ tự chạy.
- [ ] Không test private implementation detail như public contract.
- [ ] Dùng JUnit Jupiter GA tương thích với JDK mục tiêu.
- [ ] Compile/test trên JDK 26 nếu API sử dụng Java 26.
- [ ] Chỉ bật preview khi code thật sự dùng preview feature của đúng JDK.
- [ ] CI chạy contract suite trước khi publish API hoặc artifact.

## Tài liệu tham khảo

- [JUnit 6.1.3 — User Guide Overview](https://docs.junit.org/6.1.3/overview.html): cấu trúc JUnit Platform/Jupiter/Vintage, Java runtime baseline và hỗ trợ build tool.
- [JUnit 6.1.3 — Writing Tests](https://docs.junit.org/6.1.3/writing-tests/intro.html): test lifecycle, assertions, parameterized tests và test organization.
- [JUnit 6.1.3 — Release Notes](https://docs.junit.org/6.1.3/release-notes.html): các thay đổi của bản GA 6.1.3 và lịch sử release.
- [Java SE 26 — Object API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html): hợp đồng equals và các tính chất equality.
- [Java SE 26 — Comparator API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): hợp đồng compare, tính bắc cầu, đối xứng và consistency with equals.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng response lỗi có cấu trúc cho HTTP API.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): mô tả operation, request, response, schema và contract của HTTP API.

