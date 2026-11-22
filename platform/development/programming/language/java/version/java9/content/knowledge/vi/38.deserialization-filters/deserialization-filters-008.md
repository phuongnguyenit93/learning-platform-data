# Từ chối dữ liệu ngoài hợp đồng

Khi xử lý dữ liệu bằng Stream tuần tự, cần phân biệt **một phần tử không đạt điều kiện lọc nghiệp vụ** với **dữ liệu vi phạm hợp đồng đầu vào**. `filter()` dùng để chọn phần tử phù hợp: predicate trả `false` thì phần tử không đi tiếp trong pipeline. Việc đó không tự động có nghĩa dữ liệu đầu vào hợp lệ. Nếu một bản ghi vi phạm tiền điều kiện của API hoặc quy tắc cấu trúc bắt buộc, ứng dụng cần từ chối rõ ràng bằng exception hoặc trả về kết quả validation có lỗi.

Mẫu an toàn cho một batch hữu hạn là kiểm tra toàn bộ đầu vào trước, sau đó mới chạy pipeline lọc tuần tự. Cách này tận dụng tính lazy của Stream mà không để phần tử lỗi bị một `filter()` hoặc thao tác short-circuit bỏ qua. Nó cũng ngăn phần xử lý phía sau bắt đầu trên một batch mà về sau mới phát hiện có dữ liệu sai hợp đồng.

## Mục tiêu

- Phân biệt contract validation với business filtering.
- Chọn đúng cách từ chối: ném exception, trả lỗi validation, hoặc loại phần tử theo chính sách nghiệp vụ.
- Kiểm tra null, chuỗi rỗng, miền giá trị và bất biến của bản ghi.
- Hiểu vì sao validation đặt trong pipeline lazy có thể không chạy cho mọi phần tử.
- Validate toàn bộ batch trước khi lọc hoặc thực hiện side effect.
- Dùng Stream tuần tự có thứ tự xử lý rõ ràng.
- Viết predicate thuần, không dùng `filter()` như nơi giấu lỗi.
- Thiết kế thông báo lỗi có vị trí và trường vi phạm để dễ sửa dữ liệu.

## 1. Hợp đồng đầu vào là gì?

Hợp đồng đầu vào (*input contract*) mô tả điều kiện mà caller phải đáp ứng khi gọi một API hoặc gửi dữ liệu vào một quy trình. Hợp đồng có thể quy định:

- Collection đầu vào không được `null`.
- Mỗi phần tử phải tồn tại, không được `null`.
- Mã định danh phải có nội dung và đúng định dạng.
- Số lượng, giá tiền, chỉ số hoặc thời gian phải nằm trong miền hợp lệ.
- Các trường có quan hệ với nhau phải thỏa một bất biến, ví dụ ngày kết thúc không trước ngày bắt đầu.
- Giá trị enum hoặc trạng thái phải thuộc tập mà hệ thống hỗ trợ.

Ví dụ, một batch `Item` có thể yêu cầu `code` không rỗng và `quantity` lớn hơn 0. Đây là điều kiện hợp lệ của dữ liệu. Một điều kiện như `enabled == true` hoặc `quantity >= 5` có thể chỉ là tiêu chí chọn những item cần xử lý ở bước hiện tại.

Không nên gộp hai nhóm điều kiện thành một predicate duy nhất. Khi một bản ghi có `quantity == 2`, bản ghi đó có thể hợp lệ theo hợp đồng nhưng không đủ điều kiện cho một chiến dịch cần tối thiểu 5 sản phẩm. Ngược lại, `code` rỗng có thể làm bản ghi không hợp lệ dù số lượng của nó có đáp ứng tiêu chí lọc.

## 2. Từ chối hợp đồng và loại khỏi kết quả lọc

Hãy quyết định rõ ý nghĩa của từng điều kiện:

| Trường hợp | Hành vi phù hợp | Ý nghĩa |
| --- | --- | --- |
| Dữ liệu vi phạm tiền điều kiện của API | Ném exception hoặc trả validation errors | Caller đã cung cấp dữ liệu không được phép |
| Bản ghi hợp lệ nhưng không phù hợp nghiệp vụ hiện tại | `filter()` loại khỏi kết quả | Bản ghi vẫn hợp lệ, chỉ không được chọn |
| Dữ liệu hợp lệ nhưng cần chờ xử lý | Giữ lại hoặc đưa vào queue theo chính sách | Không phải lỗi hợp đồng |
| Dữ liệu có thể sửa và cần phản hồi từng trường | Trả danh sách lỗi validation | Caller có thể sửa nhiều lỗi cùng lúc |

Ví dụ:

~~~java
// Contract: quantity phải lớn hơn 0.
if (item.getQuantity() <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}

// Business rule: chỉ chọn item đang bật và có ít nhất 5 đơn vị.
boolean eligible = item.isEnabled() && item.getQuantity() >= 5;
~~~

Không dùng `filter(item -> item.getQuantity() > 0)` để che giấu dữ liệu vi phạm hợp đồng nếu caller cần biết rằng batch bị sai. Phần tử biến mất khỏi kết quả nhưng nguyên nhân không được báo, khiến lỗi dữ liệu khó phát hiện và thống kê đầu vào có thể sai.

Ngược lại, không ném exception cho mọi phần tử không đạt tiêu chí nghiệp vụ. Một phần tử hợp lệ nhưng không được chọn thường chỉ cần bị loại khỏi kết quả lọc.

## 3. Chọn exception phù hợp

Với API nhận dữ liệu trực tiếp từ caller, các kiểu lỗi thường dùng gồm:

| API/exception | Dùng khi |
| --- | --- |
| `Objects.requireNonNull(value, message)` | Một tham số bắt buộc không được `null` |
| `IllegalArgumentException` | Giá trị được truyền vào không thỏa miền hoặc định dạng được phép |
| `DateTimeParseException` | Chuỗi ngày giờ không thể phân tích theo formatter đã chọn |
| Exception validation riêng | Cần mang nhiều lỗi, mã lỗi hoặc vị trí trường có cấu trúc |

Ví dụ:

~~~java
List<Item> items = Objects.requireNonNull(input, "input must not be null");

if (item.getQuantity() <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
~~~

Thông báo nên nói rõ trường nào sai và điều kiện cần thỏa. Nếu dữ liệu đến từ file hoặc API bên ngoài, nên thêm chỉ số bản ghi, ID nguồn hoặc đường dẫn trường để caller có thể tìm đúng vị trí.

Không bắt `Exception` hoặc `Throwable` rồi bỏ qua lỗi validation. Nếu caller cần tiếp tục xử lý những bản ghi hợp lệ còn lại, hãy thể hiện đó là chính sách import có partial acceptance và trả cả danh sách accepted/rejected cùng lý do; đừng âm thầm nuốt lỗi.

## 4. Vì sao không nên chỉ validate bên trong filter?

Stream xử lý lazy. Các thao tác trung gian như `filter()`, `map()` và `peek()` chỉ tạo pipeline. Chúng chạy khi có terminal operation như `collect()`, `forEach()`, `count()` hoặc `findFirst()`.

Đoạn sau có thể không kiểm tra mọi phần tử:

~~~java
Optional<Item> first = items.stream()
    .filter(item -> {
        validate(item);
        return item.isEnabled();
    })
    .findFirst();
~~~

`findFirst()` là thao tác short-circuit. Khi đã tìm thấy phần tử phù hợp đầu tiên, stream có thể dừng. Những phần tử ở phía sau chưa chắc được kiểm tra; một dữ liệu vi phạm hợp đồng ở cuối collection có thể không bao giờ bị phát hiện.

Tương tự, `limit()`, `anyMatch()`, `noneMatch()` và `findAny()` có thể dừng pipeline trước khi tất cả dữ liệu được thăm. `count()` hoặc `collect()` thường duyệt toàn bộ với pipeline thông thường, nhưng không nên dựa vào một terminal operation cụ thể để bảo đảm validation nếu luồng có thể thay đổi thành short-circuit trong tương lai.

Đặt validation trong `peek()` còn dễ gây hiểu nhầm hơn: `peek()` được thiết kế chủ yếu để quan sát phần tử khi pipeline chạy, không phải làm ranh giới kiểm tra hợp đồng. Tác dụng phụ trong pipeline lazy phụ thuộc vào phần dữ liệu thực sự được tiêu thụ.

## 5. Validate toàn bộ batch trước khi lọc

Với một collection hữu hạn, cách rõ ràng là:

1. Kiểm tra collection và tạo snapshot các phần tử.
2. Duyệt hết snapshot để xác nhận mọi phần tử thỏa hợp đồng.
3. Nếu có lỗi, dừng và báo lỗi trước khi bắt đầu xử lý nghiệp vụ.
4. Nếu toàn bộ hợp lệ, tạo sequential stream và lọc theo tiêu chí nghiệp vụ.

~~~text
Input collection
      |
      v
Kiểm tra null và hợp đồng của mọi phần tử
      |
      +---- Có vi phạm ----> Reject batch / trả validation errors
      |
      v
Tất cả phần tử hợp lệ
      |
      v
Sequential stream.filter(businessPredicate)
      |
      v
Kết quả được chọn
~~~

Cách làm này bảo đảm một phần tử không hợp lệ ở cuối batch vẫn được phát hiện trước khi predicate nghiệp vụ hoặc side effect phía sau bắt đầu.

Snapshot bằng `new ArrayList<>(input)` giúp pipeline xử lý cùng một danh sách tham chiếu đã được chụp tại ranh giới hàm. Nếu caller có thể sửa collection đồng thời, cần quy định ownership hoặc đồng bộ lúc tạo snapshot; bản thân việc sao chép không làm các object mutable bên trong trở nên immutable.

## 6. Ví dụ Java 9: validate rồi mới lọc tuần tự

Ví dụ dưới đây quy định hợp đồng:

- Collection đầu vào không được null.
- Phần tử không được null.
- `code` phải có nội dung sau khi trim.
- `quantity` phải lớn hơn 0.

Tiêu chí lọc nghiệp vụ sau khi validation hoàn tất là item đang bật và có `quantity >= 5`. Item có `quantity == 2` vẫn hợp lệ nhưng không được chọn. Item có `code` chỉ chứa khoảng trắng vi phạm hợp đồng và làm cả batch bị từ chối.

**Tệp:** `ContractFilteringDemo.java`

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class ContractFilteringDemo {
    private static final class Item {
        private final String code;
        private final boolean enabled;
        private final int quantity;

        Item(String code, boolean enabled, int quantity) {
            this.code = code;
            this.enabled = enabled;
            this.quantity = quantity;
        }

        String getCode() {
            return code;
        }

        boolean isEnabled() {
            return enabled;
        }

        int getQuantity() {
            return quantity;
        }
    }

    private static List<Item> validateContract(List<Item> input) {
        List<Item> snapshot = new ArrayList<>(
            Objects.requireNonNull(input, "input must not be null")
        );

        for (int index = 0; index < snapshot.size(); index++) {
            Item item = Objects.requireNonNull(
                snapshot.get(index), "input[" + index + "] must not be null");

            if (item.getCode() == null || item.getCode().trim().isEmpty()) {
                throw new IllegalArgumentException(
                    "input[" + index + "].code must not be blank");
            }
            if (item.getQuantity() <= 0) {
                throw new IllegalArgumentException(
                    "input[" + index + "].quantity must be positive");
            }
        }

        return snapshot;
    }

    private static List<String> selectEligible(List<Item> input) {
        List<Item> validItems = validateContract(input);

        return validItems.stream()
            .sequential()
            .filter(Item::isEnabled)
            .filter(item -> item.getQuantity() >= 5)
            .map(Item::getCode)
            .collect(Collectors.toList());
    }

    public static void main(String[] args) {
        List<Item> validBatch = Arrays.asList(
            new Item("A-100", true, 10),
            new Item("B-200", false, 12),
            new Item("C-300", true, 2),
            new Item("D-400", true, 7)
        );
        System.out.println("eligible: " + selectEligible(validBatch));

        List<Item> invalidBatch = Arrays.asList(
            new Item("E-500", true, 8),
            new Item(" ", true, 3)
        );
        try {
            selectEligible(invalidBatch);
            throw new AssertionError("Invalid input was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("rejected: " + expected.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 ContractFilteringDemo.java
java ContractFilteringDemo
~~~

Output:

~~~text
eligible: [A-100, D-400]
rejected: input[1].code must not be blank
~~~

### 6.1. Giải thích

`validateContract()` kiểm tra collection, tạo snapshot rồi duyệt tất cả phần tử theo thứ tự index. Nếu một phần tử null hoặc có trường sai, phương thức ném exception kèm vị trí và tên trường.

`selectEligible()` chỉ tạo Stream sau khi `validateContract()` trả về thành công. `.stream()` tạo stream tuần tự; `.sequential()` thể hiện rõ pipeline được xử lý tuần tự. Hai `filter()` sau đó là tiêu chí nghiệp vụ, không còn mang trách nhiệm kiểm tra hợp đồng.

Trong batch lỗi, phần tử `E-500` đứng trước bản ghi có code rỗng. Tuy nhiên, không có kết quả lọc nào được trả về và không có hành động nghiệp vụ nào chạy trước khi validation hoàn tất. Lỗi ở phần tử thứ hai được phát hiện trước pipeline.

## 7. Khi nào nên trả danh sách validation errors thay vì fail-fast?

Ném exception ngay ở lỗi đầu tiên là phù hợp với API cần dừng khi tiền điều kiện sai, ví dụ một method nhận một cấu hình duy nhất. Với import file hoặc form có nhiều trường, caller thường muốn biết tất cả lỗi trong một lần gửi.

Có thể dùng một kiểu kết quả riêng:

~~~java
final class ValidationError {
    private final int index;
    private final String field;
    private final String message;

    // Constructor và getter được lược bỏ trong ví dụ cấu trúc.
}
~~~

Quy trình khi cần thu thập tất cả lỗi:

1. Duyệt toàn bộ input.
2. Với mỗi phần tử, kiểm tra tất cả điều kiện độc lập.
3. Thêm lỗi vào danh sách khi có vi phạm.
4. Chỉ chạy business filtering nếu danh sách lỗi rỗng, hoặc trả rõ accepted/rejected theo chính sách partial import.

Không được trả một danh sách kết quả thành công mà bỏ mất các bản ghi sai nếu caller cần biết dữ liệu đã bị từ chối. Kết quả nên thể hiện số lượng nhận, số lượng từ chối và lý do.

### 7.1. Fail-fast và aggregate validation

| Cách | Ưu điểm | Đổi lại |
| --- | --- | --- |
| Fail-fast exception | Luồng điều khiển đơn giản, dừng ngay khi hợp đồng sai | Caller thường chỉ thấy lỗi đầu tiên |
| Aggregate validation | Caller có thể sửa nhiều lỗi cùng lúc | Cần kiểu kết quả, mã lỗi và cấu trúc báo lỗi rõ ràng |
| Partial acceptance | Có thể xử lý bản ghi hợp lệ còn lại | Phải công bố rõ tính chất partial và lưu lỗi của từng bản ghi |

Chọn chính sách theo hợp đồng API. Không biến fail-fast thành partial acceptance bằng cách catch exception trong `filter()`.

## 8. Sequential stream và thứ tự xử lý

`Collection.stream()` tạo sequential stream. Với nguồn có encounter order như `List`, các phần tử được duyệt theo thứ tự encounter order khi pipeline tuần tự.

~~~java
List<String> result = items.stream()
    .sequential()
    .filter(Item::isEnabled)
    .map(Item::getCode)
    .collect(Collectors.toList());
~~~

Sequential stream phù hợp khi thứ tự đầu vào có ý nghĩa hoặc pipeline đơn giản cần xử lý tuần tự. Tuy nhiên, tuần tự không tự tạo transaction, không rollback side effect và không làm dữ liệu hợp lệ hơn. Nếu pipeline ghi database hoặc gửi message, lỗi ở phần tử sau có thể xảy ra sau khi phần tử trước đã được xử lý.

Đó là lý do cần validate batch trước mọi side effect khi hợp đồng yêu cầu từ chối toàn bộ batch nếu có bất kỳ phần tử sai nào.

## 9. Predicate nên thuần và chỉ biểu diễn điều kiện lọc

Predicate trong `filter()` nên trả lời một câu hỏi rõ ràng: phần tử hợp lệ theo nghiệp vụ hiện tại có được giữ lại không?

~~~java
Predicate<Item> eligible = item ->
    item.isEnabled() && item.getQuantity() >= 5;

List<Item> selected = validatedItems.stream()
    .filter(eligible)
    .collect(Collectors.toList());
~~~

Tránh các predicate có side effect như ghi log đồng bộ, cập nhật biến đếm dùng chung hoặc sửa phần tử đầu vào. Tránh ném exception cho điều kiện chỉ có nghĩa là “không chọn”; dùng `false` cho trường hợp loại bình thường.

Nếu predicate cần parse hoặc chuyển đổi dữ liệu có thể thất bại, hãy parse và validate ở ranh giới trước khi tạo pipeline, hoặc dùng kiểu kết quả thể hiện rõ lỗi. Không để một phép parse ngầm trong predicate khiến người đọc khó biết vì sao filter có thể ném exception.

## 10. Dữ liệu từ chuỗi, file hoặc API bên ngoài

Dữ liệu bên ngoài thường có dạng chuỗi và cần được chuyển sang kiểu miền trước khi lọc. Ví dụ:

~~~java
int quantity;
try {
    quantity = Integer.parseInt(rawQuantity);
} catch (NumberFormatException failure) {
    throw new IllegalArgumentException(
        "quantity must be an integer", failure);
}

if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
~~~

Không dùng `filter(raw -> canParse(raw))` nếu dữ liệu không parse được phải được báo cho caller. Nếu nghiệp vụ cho phép bỏ qua các dòng không parse được, đó là một chính sách import riêng; cần đếm và báo các dòng bị loại thay vì im lặng.

Với ngày giờ, dùng `java.time` và formatter được quy định; với enum, xác định tập giá trị được hỗ trợ; với số tiền, dùng `BigDecimal` và quy tắc scale/rounding rõ ràng. Không tự chuyển giá trị sai thành 0 hoặc null vì điều đó làm sai lệch ý nghĩa dữ liệu.

## 11. Short-circuit và nguồn dữ liệu không hữu hạn

Validate toàn bộ trước khi lọc phù hợp với batch hữu hạn. Với Stream vô hạn, iterator mạng hoặc nguồn dữ liệu rất lớn, không thể chờ toàn bộ nguồn rồi mới bắt đầu xử lý.

Trong trường hợp streaming, xác định contract theo từng phần tử và validate ngay trước khi phần tử đi vào phần xử lý. Cần hiểu rằng terminal operation short-circuit có thể dừng trước khi nguồn được đọc hết; do đó không thể tuyên bố toàn bộ nguồn đã được kiểm tra nếu pipeline chưa tiêu thụ toàn bộ.

Ví dụ, `findFirst()` chỉ cần phần tử đầu tiên thỏa predicate. Nó không xác nhận các phần tử sau không vi phạm hợp đồng. Nếu hệ thống cần đảm bảo toàn bộ file hoặc batch không có lỗi trước khi commit, hãy dùng giai đoạn validation riêng hoặc staging rồi commit sau khi xác nhận hoàn tất.

## 12. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `filter()` để âm thầm loại bản ghi sai hợp đồng | Caller không biết dữ liệu đã bị từ chối | Validate và báo lỗi rõ ràng trước lọc |
| Ném exception cho mọi phần tử không đạt tiêu chí nghiệp vụ | Nhầm loại bình thường với vi phạm contract | Predicate trả false cho trường hợp hợp lệ nhưng không được chọn |
| Đặt validation trong pipeline rồi gọi `findFirst()` | Short-circuit có thể bỏ qua phần tử lỗi ở phía sau | Validate toàn bộ batch trước pipeline |
| Dùng `peek()` để kiểm tra hợp đồng | `peek()` lazy và chỉ chạy khi phần tử được tiêu thụ | Dùng bước validation tường minh |
| Bắt exception rồi tiếp tục như không có lỗi | Dữ liệu sai bị mất dấu và kết quả không phản ánh batch | Fail-fast hoặc trả rejected items kèm lý do |
| Chỉ kiểm tra phần tử được filter giữ lại | Bản ghi bị loại có thể vẫn vi phạm contract | Validate trước khi áp dụng business predicate |
| Cho rằng stream tuần tự bảo đảm rollback | Sequential chỉ nói về cách xử lý, không phải transaction | Validate trước side effect; dùng transaction/staging khi cần atomic batch |
| Dùng mutable object rồi sửa trong lúc lọc | Kết quả phụ thuộc thời điểm và có thể gây race | Dùng immutable DTO hoặc đồng bộ ownership |
| Chuyển dữ liệu sai thành giá trị mặc định | Che giấu lỗi nguồn và làm sai nghĩa nghiệp vụ | Giữ nguyên lỗi parse/validation và báo vị trí |
| Giả định `findFirst()` đã kiểm tra toàn bộ nguồn | Đây là thao tác short-circuit | Chỉ tuyên bố full validation sau khi duyệt hết nguồn |

## 13. Quy tắc thực hành

1. Viết rõ contract của collection và từng phần tử tại ranh giới API.
2. Dùng `Objects.requireNonNull()` cho tham số bắt buộc không được null.
3. Dùng `IllegalArgumentException` hoặc lỗi domain có cấu trúc cho giá trị ngoài miền cho phép.
4. Phân biệt contract violation với điều kiện nghiệp vụ dùng để chọn phần tử.
5. Với batch hữu hạn, validate toàn bộ trước khi tạo pipeline lọc.
6. Dùng `.stream()` hoặc `.sequential()` khi cần xử lý tuần tự theo encounter order.
7. Giữ predicate thuần, không có side effect và không giấu lỗi parse.
8. Không dựa vào `peek()` hoặc short-circuit operation để xác nhận toàn bộ batch.
9. Nếu cần báo nhiều lỗi, trả aggregate validation result; nếu partial acceptance, công bố rõ các bản ghi bị từ chối.
10. Validate trước khi ghi database, gửi message hoặc thực hiện side effect không thể rollback.
11. Dùng immutable input hoặc snapshot ổn định khi xử lý batch.
12. Ghi vị trí và tên trường trong thông báo lỗi để caller sửa đúng dữ liệu.

## 14. Tự kiểm tra

- `filter()` làm gì khi predicate trả `false`? Loại phần tử khỏi kết quả pipeline.
- Một bản ghi hợp lệ nhưng không đạt tiêu chí nghiệp vụ có nên ném exception không? Thông thường không; predicate trả false.
- Khi nào cần từ chối bằng exception? Khi dữ liệu vi phạm tiền điều kiện hoặc invariant của hợp đồng.
- Vì sao validation trong `filter()` có thể bỏ sót lỗi? Pipeline lazy và terminal operation short-circuit có thể dừng sớm.
- Làm sao bảo đảm mọi phần tử của batch hữu hạn đều được kiểm tra trước khi lọc? Duyệt và validate toàn bộ batch trước khi tạo pipeline nghiệp vụ.
- `.stream()` của List có phải parallel không? Không, đó là sequential stream.
- Sequential stream có tự rollback side effect không? Không.
- `peek()` có phù hợp làm validation boundary không? Không; nó là thao tác trung gian phục vụ quan sát.
- Khi cần báo tất cả lỗi thì dùng cách nào? Aggregate validation result với vị trí/trường/mã lỗi.
- Khi nào partial acceptance phù hợp? Khi hợp đồng import công bố rõ việc nhận bản ghi hợp lệ và trả đầy đủ rejected items cùng lý do.
- Có thể khẳng định một nguồn vô hạn đã được validate toàn bộ sau `findFirst()` không? Không.

Điểm cốt lõi: **`filter()` chọn dữ liệu hợp lệ theo nghiệp vụ; validation từ chối dữ liệu vi phạm hợp đồng.** Với batch hữu hạn, hãy validate toàn bộ trước rồi mới lọc tuần tự để không che giấu lỗi ở những phần tử phía sau.