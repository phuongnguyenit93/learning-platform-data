# Quy ước đặt tên biến, tham số và hằng trong Java 17+

## 1. Vì sao quy ước đặt tên quan trọng?

Tên biến, tham số và hằng là một phần của cách diễn đạt ý nghĩa chương trình. Java **kiểm tra tên có hợp lệ về cú pháp**, còn **quy ước đặt tên** giúp người khác hiểu dữ liệu, giảm nhầm lẫn và dễ tìm kiếm khi bảo trì.

~~~java
int x = 3;                   // Hợp lệ nhưng khó biết x là gì
int itemCount = 3;           // Cùng kiểu dữ liệu, rõ nghĩa hơn

int p = 120_000;             // Không thấy đơn vị hoặc vai trò
int unitPriceDong = 120_000; // Cho biết đây là đơn giá tính bằng đồng
~~~

Ba nguyên tắc thực dụng:

1. **Đúng cú pháp Java**: tên không được là từ khóa hoặc literal bị dành riêng, không bắt đầu bằng chữ số và phải tuân theo quy tắc định danh.
2. **Rõ vai trò**: tên nêu dữ liệu hoặc ý định nghiệp vụ thay vì chỉ lặp lại tên kiểu.
3. **Nhất quán trong toàn dự án**: cùng một khái niệm nên được gọi thống nhất, tránh đổi giữa `amount`, `value`, `money` mà không có lý do.

Tên “đúng chuẩn” không bảo đảm chương trình đúng nghiệp vụ; nhưng tên kém rõ ràng có thể che khuất lỗi ngay cả khi chương trình vẫn biên dịch.

## 2. Bảng quy ước thường dùng

| Thành phần | Phong cách thông dụng | Ví dụ nên dùng | Tránh khi không có lý do |
|---|---|---|---|
| Biến cục bộ | `lowerCamelCase` | `itemCount`, `totalPriceDong` | `ItemCount`, `item_count` |
| Tham số method | `lowerCamelCase` | `unitPriceDong`, `discountPercent` | `UnitPrice`, `arg1` |
| Field instance | `lowerCamelCase` | `customerName`, `isActive` | `CUSTOMER_NAME` cho field thông thường |
| Field static thay đổi được | `lowerCamelCase` | `requestCount` | `REQUEST_COUNT` nếu không phải hằng |
| Hằng được đặt tên | `UPPER_SNAKE_CASE` | `MAX_ITEMS`, `DEFAULT_TIMEOUT_MS` | `max_items`, `DefaultTimeoutMs` |
| Biến cục bộ `final` | Thường vẫn `lowerCamelCase` | `final int maxAllowed = 5;` | Mặc định đổi mọi final local thành `MAX_ALLOWED` |
| Hằng enum | Thường `UPPER_SNAKE_CASE` | `PENDING`, `IN_PROGRESS` | Viết mỗi giá trị một kiểu tên |

Đây là **convention**, không phải bộ quy tắc được `javac` ép buộc. Ví dụ `int ItemCount = 3;` có thể biên dịch nhưng phá vỡ phong cách chung. Các công cụ lint/style có thể áp dụng quy ước chặt hơn theo dự án.

**`lowerCamelCase`**: từ đầu viết thường, các từ tiếp theo viết hoa chữ cái đầu: `maxRetryCount`.

**`UPPER_SNAKE_CASE`**: các từ viết hoa, phân cách bằng `_`: `MAX_RETRY_COUNT`.

## 3. Phân biệt tên hợp lệ và tên nên dùng

Java phân biệt chữ hoa/chữ thường, do đó `count`, `Count` và `COUNT` là **ba định danh khác nhau**. Nhưng dùng cả ba trong cùng phạm vi rất dễ gây hiểu nhầm.

~~~java
int count = 3;
// int Count = 4; // Có thể hợp lệ, nhưng không nên tạo cặp tên quá giống nhau
~~~

Các trường hợp đáng nhớ:

| Định danh | Hợp lệ làm tên biến? | Đánh giá |
|---|---|---|
| `itemCount` | Có | Đúng quy ước và rõ nghĩa |
| `_itemCount` | Có | Thường không cần dấu `_` ở đầu |
| `$itemCount` | Có | Java cho phép `$`, nhưng nên tránh dùng tùy tiện |
| `sốLượng` | Có | Java hỗ trợ Unicode; dự án cần quy ước nhất quán |
| `2items` | Không | Bắt đầu bằng chữ số |
| `item-count` | Không phải một định danh | Dấu `-` là toán tử |
| `item count` | Không | Có khoảng trắng |
| `class` | Không | Từ khóa Java |
| `true` | Không | Boolean literal dành riêng |
| `_` | Không trên Java 17 | Dấu gạch dưới đơn lẻ bị dành riêng |

Một tên hợp lệ vẫn phải được đặt **đúng phạm vi** và **không trùng khai báo trái quy tắc**. Trong một block không thể khai báo hai biến cục bộ cùng tên.

`String` và `string` không phải cùng định danh; khi đặt tên nên tránh phụ thuộc vào người đọc “đoán” chữ hoa/chữ thường.

## 4. Đặt tên biến theo nghĩa, đơn vị và trạng thái

Tên biến nên trả lời được câu hỏi “giá trị này biểu thị điều gì?”:

~~~java
int itemCount = 3;
long totalPriceDong = 360_000L;
int timeoutMillis = 2_500;
double distanceKilometers = 12.5;
String customerEmail = "lan@example.com";
~~~

Nếu hai giá trị cùng kiểu nhưng khác **đơn vị**, tên nên chỉ ra đơn vị:

~~~java
long timeoutMillis = 500;
long timeoutSeconds = 2;

// Không được xem 500 và 2 là cùng một đơn vị chỉ vì đều là long.
~~~

Với những miền quan trọng như thời gian và tiền tệ, có thể dùng kiểu chuyên biệt (ví dụ `Duration`, `BigDecimal`) thay cho một con số trần. Nhưng khi dùng primitive, tên có đơn vị vẫn giúp giảm lỗi.

**Tránh những tên không mang nội dung**: `data`, `value`, `obj`, `temp`, `str` khi bạn có thể dùng một danh từ cụ thể hơn. Biến vòng lặp ngắn `i` có thể chấp nhận trong đoạn 2–3 dòng rất rõ ngữ cảnh; với vòng lặp dài, `itemIndex` hoặc `orderIndex` dễ hiểu hơn.

### Tên boolean như một câu hỏi đúng/sai

Biến `boolean` thường nên đọc như một mệnh đề:

~~~java
boolean isActive = true;
boolean hasPermission = false;
boolean canSubmit = isActive && hasPermission;
boolean isEmpty = itemCount == 0;
~~~

Các tiền tố `is`, `has`, `can`, `should` giúp người đọc hiểu phép kiểm tra:

~~~java
if (hasPermission && isActive) {
    System.out.println("ALLOW");
}
~~~

Đừng đặt `isActive` cho một biến số lượng hoặc một chuỗi; tên phải khớp với kiểu và ý nghĩa thực.

Không bắt buộc mọi boolean phải bắt đầu bằng `is`. Các tên tự nhiên như `enabled`, `valid` có thể vẫn rõ nghĩa khi thống nhất trong codebase.

## 5. Tên tham số: diễn tả hợp đồng của method

Tham số giúp người gọi hiểu **đầu vào** của phương thức. Chọn tên bộc lộ vai trò, miền giá trị và đơn vị:

~~~java
static long calculateTotalDong(
        int unitPriceDong,
        int itemCount,
        int discountPercent) {
    if (unitPriceDong < 0 || itemCount < 0
            || discountPercent < 0 || discountPercent > 100) {
        throw new IllegalArgumentException("Invalid input");
    }

    long subtotalDong = (long) unitPriceDong * itemCount;
    return subtotalDong * (100 - discountPercent) / 100;
}
~~~

`unitPriceDong`, `itemCount` và `discountPercent` giúp người đọc phân biệt **đơn giá**, **số lượng** và **phần trăm giảm**, dù tất cả đều là `int`.

Nếu tham số được đặt tên `a`, `b`, `c`, chữ ký có thể vẫn biên dịch nhưng người gọi phải mở thân method mới hiểu ý nghĩa.

### Tránh tên tham số che khuất field nếu không có chủ đích

Một tình huống hợp lệ:

~~~java
class Order {
    private int itemCount;

    Order(int itemCount) {
        this.itemCount = itemCount;
    }
}
~~~

Tham số và field cùng tên là lựa chọn phổ biến; `this.itemCount` giúp nói rõ field, còn `itemCount` chỉ tham số. Không cần đổi thành `theItemCount` hay `pItemCount` chỉ để né việc dùng `this`.

Tuy nhiên, ngoài những trường hợp có chủ đích như constructor/setter, cần tránh che khuất tên khiến mã trở nên khó hiểu.

## 6. Hằng: tên in hoa và dấu gạch dưới

Khi một giá trị cố định có ý nghĩa và được dùng lại, đặt tên hằng giúp tránh **magic numbers**:

~~~java
private static final int MAX_ITEMS = 5;
private static final int DEFAULT_DISCOUNT_PERCENT = 10;
private static final String CURRENCY_CODE = "VND";
~~~

Ví dụ:

~~~java
if (itemCount > MAX_ITEMS) {
    throw new IllegalArgumentException("Too many items");
}
~~~

Tên `MAX_ITEMS` mô tả vai trò của số `5`; tên `DEFAULT_DISCOUNT_PERCENT` nhắc rằng giá trị `10` là **phần trăm**, không phải số tiền.

### `final` không đồng nghĩa mọi biến phải viết hoa

~~~java
final int selectedItemCount = 3;   // final local: lowerCamelCase
private static final int MAX_ITEMS = 5; // named constant: UPPER_SNAKE_CASE
~~~

`final` là **quy tắc ngôn ngữ** giới hạn việc gán lại biến; còn `UPPER_SNAKE_CASE` là **quy ước tên** cho các hằng được đặt tên.

Với `static final` là tham chiếu đến đối tượng mutable, việc không gán lại biến **không** khiến trạng thái của object bất biến. Vì thế, không nên chỉ nhìn tên viết hoa rồi suy đoán dữ liệu chắc chắn bất biến.

Các framework/nhóm có thể có ngoại lệ (ví dụ một `static final Logger logger` đặt `lowerCamelCase`). Hãy tuân theo style đã thống nhất thay vì áp dụng bảng một cách máy móc.

### Hằng liên quan đến đơn vị

Tên rõ đơn vị giúp người đọc tự kiểm tra khi dùng API:

~~~java
private static final long REQUEST_TIMEOUT_MILLIS = 3_000L;
private static final int MAX_RETRY_COUNT = 3;
~~~

Tránh tên `TIMEOUT` khi không rõ là giây hay mili-giây. Hãy dùng cùng một từ cho cùng một khái niệm trong toàn hệ thống.

## 7. Chương trình Java 17 chạy được

Lưu toàn bộ mã dưới đây vào **`NamingConventionDemo.java`**:

~~~java
public final class NamingConventionDemo {
    private static final int MAX_ITEMS = 5;
    private static final int DEFAULT_DISCOUNT_PERCENT = 10;
    private static final String CURRENCY_CODE = "VND";

    private NamingConventionDemo() {}

    static long calculateTotalDong(
            int unitPriceDong, int itemCount, int discountPercent) {
        if (unitPriceDong < 0 || itemCount < 0 || itemCount > MAX_ITEMS) {
            throw new IllegalArgumentException("Invalid item count or price");
        }
        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("Invalid discount percent");
        }
        long subtotalDong = (long) unitPriceDong * itemCount;
        return subtotalDong * (100 - discountPercent) / 100;
    }

    static boolean canCheckout(boolean isActive, boolean hasPermission) {
        return isActive && hasPermission;
    }

    public static void main(String[] args) {
        int unitPriceDong = 120_000;
        int itemCount = 3;
        int discountPercent = DEFAULT_DISCOUNT_PERCENT;
        boolean isExpressDelivery = false;

        long totalDong = calculateTotalDong(
                unitPriceDong, itemCount, discountPercent);
        boolean isActive = true;
        boolean hasPermission = true;

        System.out.println("itemCount=" + itemCount);
        System.out.println("unitPriceDong=" + unitPriceDong);
        System.out.println("discountPercent=" + discountPercent);
        System.out.println("totalDong=" + totalDong);
        System.out.println("currency=" + CURRENCY_CODE);
        System.out.println("isExpressDelivery=" + isExpressDelivery);
        System.out.println("canCheckout=" +
                canCheckout(isActive, hasPermission));
        System.out.println("maxItems=" + MAX_ITEMS);
    }
}
~~~

Mở terminal tại thư mục chứa tệp và sử dụng **JDK 17 hoặc mới hơn**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NamingConventionDemo.java
java -cp . NamingConventionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NamingConventionDemo.java
java -cp . NamingConventionDemo
~~~

**Expected output:**

~~~text
itemCount=3
unitPriceDong=120000
discountPercent=10
totalDong=324000
currency=VND
isExpressDelivery=false
canCheckout=true
maxItems=5
~~~

Lý do:

- `itemCount`, `unitPriceDong`, `discountPercent`, `totalDong` là các tên biến `lowerCamelCase` có ý nghĩa.
- Các tham số của `calculateTotalDong` cũng sử dụng `lowerCamelCase`.
- `MAX_ITEMS`, `DEFAULT_DISCOUNT_PERCENT`, `CURRENCY_CODE` là các hằng được đặt tên theo `UPPER_SNAKE_CASE`.
- `isActive`, `hasPermission`, `canCheckout` diễn đạt trạng thái/điều kiện boolean.
- `totalDong = 120000 × 3 × (100 - 10) / 100 = 324000` được tính bằng `long` trước khi chia.

Ví dụ tập trung vào quy ước đặt tên. Trong ứng dụng thật, hãy kiểm thử cả dữ liệu biên và xác định quy tắc làm tròn tiền theo hợp đồng nghiệp vụ.

## 8. Nhất quán tên trong API và lúc đổi tên

Giả sử nhiều method dùng chung khái niệm “số lượng sản phẩm”:

~~~java
int itemCount = 3;
void updateItemCount(int itemCount) { /* ... */ }
int getItemCount() { return itemCount; }
~~~

Đoạn trên chỉ nhằm minh họa tên: các method cần được đặt trong một class hợp lệ, với field thích hợp nếu muốn dùng chúng như code hoàn chỉnh.

Nhất quán `itemCount` tốt hơn dùng `num`, `qty`, `size` và `count` lẫn lộn khi tất cả cùng chỉ số món hàng. Tuy nhiên, `itemCount` và `cartSize` có thể là hai khái niệm khác nhau nếu mô hình nghiệp vụ thật sự khác.

### Khi rename

- Đổi tên biến cục bộ và tham số bằng chức năng **Rename Refactor** của IDE khi có thể.
- Nếu đổi tên hằng `MAX_ITEMS`, cập nhật mọi nơi tham chiếu tương ứng.
- Nếu đổi tên public method/field trong API, kiểm tra tác động đến caller, test, reflection, serialization và tài liệu.
- Java phân biệt hoa/thường nên `maxItems` không tự biến thành `MAX_ITEMS`; thay đổi chỉ một chữ hoa cũng là đổi định danh.

Tên không cần hoàn hảo ngay lần đầu, nhưng nên cải thiện khi hiểu chính xác ý nghĩa dữ liệu và trước khi tên trở thành API mà nhiều nơi phụ thuộc.

## 9. Các tên dễ gây nhầm và phương án tốt hơn

| Tên kém rõ | Tên tốt hơn | Điều được làm rõ |
|---|---|---|
| `n` | `itemCount` | Đại lượng được đếm |
| `p` | `unitPriceDong` | Đơn giá và đơn vị |
| `t` | `timeoutMillis` | Thời lượng và đơn vị |
| `flag` | `isActive` | Trạng thái boolean |
| `x1` | `discountPercent` | Vai trò trong phép tính |
| `MAX` | `MAX_ITEMS` | Giới hạn cái gì |
| `DEFAULT` | `DEFAULT_DISCOUNT_PERCENT` | Giá trị mặc định của trường nào |
| `list` | `customerEmails` | Kiểu dữ liệu/chứa gì ở mức nghiệp vụ |
| `result` | `totalDong` | Kết quả có ý nghĩa gì |

Các tên ngắn không phải lúc nào cũng sai. Biến `i` trong vòng lặp hai dòng có thể đủ rõ. Nhưng một tham số thuộc public API tên `x` nên được xem xét kỹ hơn vì người đọc cần hiểu hợp đồng khi gọi method.

**Tránh tên khiến người đọc suy luận sai kiểu hoặc hành vi**: đừng gọi biến số `isReady` nếu nó chứa `int`, đừng gọi timeout tính bằng mili-giây là `timeoutSeconds`.

## 10. Một số lỗi về naming convention cần phân biệt

| Hiện tượng | Là lỗi compiler hay lỗi convention? | Cách xử lý |
|---|---|---|
| `int 2count = 3;` | Lỗi cú pháp | `int count2 = 3;` |
| `int class = 1;` | Lỗi cú pháp vì từ khóa | `int classCount = 1;` |
| `int count_value = 3;` | Có thể biên dịch, sai style thông dụng | `int countValue = 3;` |
| `int Count = 3;` | Có thể biên dịch, tên biến không theo convention | `int count = 3;` |
| `static final int maxItems = 5;` | Có thể biên dịch, tên hằng không nhất quán | `MAX_ITEMS` nếu thực sự là named constant |
| `MAX_ITEMS` và `maxItems` dùng lẫn | Hai định danh khác nhau | Thống nhất ý nghĩa và rename chính xác |
| Đặt `isEnabled` cho `int` | Có thể biên dịch nhưng đánh lừa người đọc | Tên như `enabledItemCount` |
| `TIMEOUT_MS` nhưng giá trị tính bằng giây | Lỗi ý nghĩa, compiler khó phát hiện | Đổi đơn vị/giá trị và tên đồng bộ |

**Compiler báo “cannot find symbol”** có thể xuất phát từ gõ sai chữ hoa/thường khi tham chiếu tên, chứ không phải vì Java bắt `lowerCamelCase`.

## 11. Bài tập có đáp án

### Bài A — đổi tên theo lowerCamelCase

Đổi các tên biến `Total_Price`, `customer_name`, `numberOf_Items` thành tên theo quy ước, giả sử ý nghĩa tương ứng không đổi.

**Đáp án gợi ý:** `totalPrice`, `customerName`, `numberOfItems`. Nếu giá có đơn vị cụ thể, có thể tốt hơn nữa: `totalPriceDong`.

### Bài B — phân biệt final local và named constant

~~~java
final int retryCount = 3;
static final int MAX_RETRIES = 3;
~~~

**Đáp án:** tên `retryCount` theo `lowerCamelCase` phù hợp cho final local; `MAX_RETRIES` theo `UPPER_SNAKE_CASE` phù hợp cho hằng `static final` của class. Dòng thứ hai phải được đặt ở vị trí khai báo field hợp lệ, không đặt `static` trong block method.

### Bài C — tên boolean

Chọn tên rõ ràng cho ba trạng thái: người dùng đã đăng nhập, tài khoản bị khóa, có thể gửi đơn.

**Đáp án gợi ý:** `isLoggedIn`, `isAccountLocked`, `canSubmitOrder`; dùng kiểu `boolean`.

### Bài D — đơn vị không được bỏ qua

Một tham số nhận thời gian chờ tính bằng mili-giây tên `timeout`. Tên nào rõ hơn?

**Đáp án:** `timeoutMillis` hoặc `timeoutMilliseconds`, nhất quán với quy ước của dự án. Nếu dùng kiểu `Duration`, tên `timeout` có thể đủ rõ vì kiểu đã mang ý nghĩa thời lượng.

### Bài E — tên hợp lệ nhưng khó đọc

~~~java
int a = 3;
int b = 120000;
long c = (long) a * b;
~~~

Hãy đổi tên để người đọc hiểu đơn vị và vai trò.

**Đáp án gợi ý:**

~~~java
int itemCount = 3;
int unitPriceDong = 120000;
long subtotalDong = (long) itemCount * unitPriceDong;
~~~

Không đổi công thức; chỉ dùng tên giúp giải thích điều đang được tính.

## 12. Checklist và kết luận

- [ ] Phân biệt quy tắc cú pháp bắt buộc với naming convention.
- [ ] Dùng `lowerCamelCase` nhất quán cho biến và tham số.
- [ ] Dùng `UPPER_SNAKE_CASE` cho hằng có tên khi phù hợp với style của nhóm.
- [ ] Hiểu `final` không tự buộc mọi tên biến phải in hoa.
- [ ] Đặt tên thể hiện đại lượng, đơn vị và trạng thái boolean.
- [ ] Không dùng tên quá giống nhau chỉ khác chữ hoa/thường.
- [ ] Phân biệt tên tham số và field có chủ đích bằng `this`.
- [ ] Tránh magic numbers bằng tên hằng có ý nghĩa.
- [ ] Biên dịch và chạy `NamingConventionDemo.java` trên JDK 17+, đối chiếu output.
- [ ] Dùng rename refactoring để thay đổi tên nhất quán và kiểm tra tác động đến API.

**Kết luận:** Tên biến và tham số nên mô tả **dữ liệu hoặc vai trò** theo `lowerCamelCase`; hằng được đặt tên thường dùng `UPPER_SNAKE_CASE`. Đây là quy ước giúp mã rõ ràng và nhất quán, không phải phép màu làm chương trình tự đúng. Hãy kết hợp tên dễ đọc với kiểu phù hợp, đơn vị minh bạch và kiểm thử hành vi thực tế.