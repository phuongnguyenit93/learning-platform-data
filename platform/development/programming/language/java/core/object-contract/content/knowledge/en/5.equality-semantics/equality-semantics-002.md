# Chọn trường thực sự quyết định giá trị của đối tượng

## 1. Chọn trường bắt đầu từ định nghĩa “bằng nhau”

Trong Java, `equals(Object)` và `hashCode()` phải phản ánh ý nghĩa của đối tượng trong bài toán, không đơn thuần so sánh mọi trường vì chúng đang có mặt trong lớp. Câu hỏi quan trọng nhất là: **Nếu hai object khác giá trị ở trường X, chúng có còn được coi là cùng một thực thể hoặc cùng một giá trị theo quy tắc nghiệp vụ hay không?**

Ví dụ, hai tài khoản có cùng mã tài khoản nhưng tên hiển thị khác nhau có thể vẫn là cùng tài khoản. Ngược lại, hai đơn hàng có tổng tiền giống hệt nhưng mã đơn khác nhau vẫn là hai đơn hàng. Hai tọa độ `Point(2, 3)` có thể được xem là cùng giá trị dù là hai object được tạo bằng hai lệnh `new` riêng.

Vì vậy, hãy **viết một câu định nghĩa bình đẳng bằng ngôn ngữ nghiệp vụ trước khi viết code**:

- “Hai tài khoản bằng nhau nếu mã tài khoản bất biến giống nhau trong cùng phạm vi định danh.”
- “Hai số tiền bằng nhau nếu đơn vị tiền tệ và số lượng đơn vị nhỏ nhất đều giống nhau.”
- “Hai khóa đặt phòng bằng nhau nếu cùng khách sạn, ngày nhận phòng và mã phòng.”
- “Hai phiên kết nối chỉ là một nếu cùng instance tài nguyên” (trường hợp nên giữ identity mặc định).

Lớp có thể mang nhiều trường nhưng chỉ một tập con thực sự quyết định identity hoặc value. Tập con này phải được sử dụng **nhất quán giữa `equals()` và `hashCode()`**.

## 2. Ba cách nhìn đối tượng

| Mô hình | Khi nào hai object bằng nhau? | Trường nên dùng |
| --- | --- | --- |
| **Entity (thực thể)** | Đại diện cùng thực thể theo thời gian, dù trạng thái có thay đổi | Định danh ổn định, đủ duy nhất trong phạm vi nghiệp vụ |
| **Value object** | Mang cùng giá trị được mô tả bởi các thành phần | Tất cả các thuộc tính thật sự làm nên giá trị |
| **Identity object** | Chính xác là cùng instance | Có thể giữ `Object.equals()` và `Object.hashCode()` |

**Entity:** Với `Account(accountId, displayName, loginCount)`, giả sử domain quy định `accountId` là mã bất biến và duy nhất. Nếu `displayName` đổi từ “An” sang “An Nguyễn”, tài khoản không biến thành tài khoản khác. Nếu `loginCount` tăng từ 4 lên 5, identity cũng không thay đổi. Khi đó chỉ `accountId` được chọn để so sánh.

**Value object:** Với `Money(currency, minorUnits)`, cả hai thành phần quyết định giá trị: `Money("VND", 100_000)` khác `Money("USD", 100_000)`. Chỉ so số lượng tiền làm mất thông tin đơn vị; chỉ so đơn vị cũng không đủ.

**Identity mặc định:** Hai đối tượng đại diện hai session đang mở có thể cùng URL, account hay cấu hình nhưng vẫn là hai tài nguyên runtime riêng. Nếu không có nhu cầu so bình đẳng logic, giữ nguyên `Object.equals()` theo tham chiếu (`==`) là quyết định có cơ sở.

Tên lớp không tự xác định mô hình. Một lớp tên `User` có thể có ID từ khi khởi tạo, hoặc chỉ được cấp ID khi ghi database. Thiết kế equality phải hiểu vòng đời đó.

## 3. Bảng tiêu chí chọn hoặc loại từng trường

Hãy phân loại từng thuộc tính thay vì tự động chọn tất cả:

| Loại trường | Thường có tham gia equality không? | Câu hỏi để quyết định |
| --- | --- | --- |
| ID bất biến, duy nhất | Có với entity | ID có đủ duy nhất trong tenant/phạm vi đang so sánh? |
| Thành phần giá trị cốt lõi | Có với value object | Bỏ nó có làm hai giá trị khác nghĩa bị coi là một? |
| Tên hiển thị hoặc mô tả | Thường không với entity | Đổi tên có đổi identity không? |
| `updatedAt`, `lastLoginAt`, bộ đếm | Thường không với entity | Thay đổi hoạt động có tạo thực thể mới không? |
| Cache hoặc trường tính từ dữ liệu khác | Thường không | Nó có mang thông tin mới hay chỉ là dữ liệu phái sinh? |
| Collection chứa dữ liệu giá trị | Có thể có | Cần so thứ tự, tập phần tử hay snapshot nào? Nội dung có thay đổi không? |
| Khóa database được cấp sau `persist` | Cần chính sách vòng đời | Trước khi có ID, hai entity mới được so thế nào? |
| Trường trong superclass | Tùy quy tắc toàn hierarchy | Có đảm bảo đối xứng, bắc cầu khi so lớp cha và con? |

Để thử một lựa chọn, tự đặt ra hai tình huống phản chứng:

1. **Bỏ sót trường:** Giữ nguyên toàn bộ trường đã chọn, thay trường X bị loại. Có trường hợp nào hai object **phải khác nhau** mà `equals()` lại cho `true` không?
2. **Thừa trường:** Giữ nguyên định danh/các thành phần giá trị, thay trường Y đã chọn. Có trường hợp nào hai object **phải vẫn bằng nhau** mà `equals()` lại cho `false` không?

Ví dụ khóa phòng có thể là `(hotelId, roomNo)`; nếu chỉ chọn `roomNo` thì phòng “101” ở hai khách sạn bị coi là một. Một mã `accountId` chỉ duy nhất trong từng tenant cũng cần thêm `tenantId` vào khóa so sánh. Ngược lại, nếu ID đã duy nhất toàn hệ thống thì các trường mô tả có thể không cần tham gia equality.

## 4. Các hợp đồng của Java phải bảo toàn

`Object.equals()` có các yêu cầu:

1. **Reflexive:** `x.equals(x)` luôn `true` đối với `x` khác null.
2. **Symmetric:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Transitive:** nếu `x` bằng `y` và `y` bằng `z` thì `x` bằng `z`.
4. **Consistent:** các lần so sánh cho kết quả ổn định khi các thuộc tính liên quan không đổi.
5. **Non-null:** `x.equals(null)` phải `false`.

`Object.hashCode()` yêu cầu: khi `x.equals(y)` là `true`, **`x.hashCode() == y.hashCode()` cũng phải là `true`**. Chiều ngược lại không bắt buộc: trùng hash không chứng minh hai object bằng nhau. Collision là hiện tượng được phép.

Nếu `equals()` chỉ dùng `id` nhưng `hashCode()` lại dùng `id` và `displayName`, hai object bằng nhau có thể tạo hash khác nhau, vi phạm contract. Hãy tính hash từ cùng tập trường đã chọn; không thêm timestamp, tên hiển thị hay số ngẫu nhiên chỉ để “tránh trùng hash”.

Một chú ý khác: **hash của key không nên thay đổi khi key nằm trong `HashMap` hoặc `HashSet`**. Collection dùng hash để tìm bucket; nếu trường tham gia hash thay đổi sau khi insert, `contains()` hoặc `get()` có thể thất bại ngay với cùng object. `final` giúp ngăn gán lại trường, nhưng `final List<String>` vẫn cho phép thay đổi nội dung list được tham chiếu. Bất biến phải xét cả đồ thị đối tượng có liên quan.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Chương trình dưới đây minh họa hai mô hình: entity `Account` chỉ dùng định danh, value object `Money` dùng toàn bộ thành phần giá trị. Tạo tệp `EqualityFieldsDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityFieldsDemo {

    static final class Account {
        private final String accountId;
        private String displayName;
        private int loginCount;

        Account(String accountId, String displayName) {
            this.accountId = Objects.requireNonNull(accountId);
            if (accountId.isBlank()) {
                throw new IllegalArgumentException("accountId must not be blank");
            }
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        void recordLogin() {
            loginCount++;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Account)) return false;
            Account that = (Account) other;
            return accountId.equals(that.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }
    }

    // Cả hai thành phần của record là thành phần giá trị.
    record Money(String currency, long minorUnits) {
        Money {
            Objects.requireNonNull(currency);
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency must not be blank");
            }
        }
    }

    public static void main(String[] args) {
        Account a = new Account("ACC-01", "An");
        Account b = new Account("ACC-01", "Tên khác");
        Account c = new Account("ACC-02", "An");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));

        Set<Account> accounts = new HashSet<>();
        accounts.add(a);
        accounts.add(b);
        accounts.add(c);
        System.out.println(accounts.size());

        a.rename("An Nguyễn");
        a.recordLogin();
        System.out.println(accounts.contains(a));
        System.out.println(accounts.contains(b));

        Money m1 = new Money("VND", 100_000);
        Money m2 = new Money("VND", 100_000);
        Money m3 = new Money("USD", 100_000);
        System.out.println(m1.equals(m2));
        System.out.println(m1.equals(m3));
        System.out.println(m1.hashCode() == m2.hashCode());
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

Biên dịch và chạy:

```bash
javac EqualityFieldsDemo.java
java EqualityFieldsDemo
```

Stdout:

```text
true
false
2
true
true
true
false
true
true
```

Giải thích kết quả theo thứ tự:

- `a` và `b` khác instance và khác tên nhưng cùng `accountId`, nên `equals()` trả về `true`. `a` và `c` khác ID, nên `false`.
- `HashSet` giữ hai phần tử logic: tài khoản `ACC-01` và `ACC-02`. Việc thêm `b` không làm tăng số lượng vì `a` đã đại diện cùng identity.
- Khi đổi tên và tăng bộ đếm của `a`, key identity không đổi nên `accounts.contains(a)` vẫn `true`; một instance khác có cùng ID (`b`) cũng được nhận diện.
- `Money` là `record`. Java tự tạo `equals()` và `hashCode()` từ các record component; hai giá trị cùng mã tiền và số lượng bằng nhau, khác mã tiền thì không.
- Hai object được `equals()` coi là bằng nhau phải có cùng hash. Nhưng hai object có hash bằng nhau chưa chắc bằng nhau.

Trong ví dụ, `Account` là `final` nên không có subclass bổ sung thuộc tính rồi thay chính sách equality. `accountId` là `String` bất biến và không thay đổi sau constructor. `displayName` và `loginCount` mutable nhưng không tham gia equality. Đó là lý do chính sách giữ ổn định với `HashSet`.

**Cần hiểu giới hạn của `record`:** Record tạo equality theo **tất cả record component**, không biết component nào có vai trò nghiệp vụ. Một component là nhãn hiển thị hoặc cache nếu được đặt trong record sẽ ảnh hưởng equality mặc định. Record không tự biến object mutable được tham chiếu trong component thành immutable.

## 6. Bẫy thường gặp khi chọn trường

### 6.1. Chọn mọi trường có sẵn vì IDE đề nghị

Một class entity có 10 trường không có nghĩa tất cả 10 trường quyết định identity. `name`, `status`, `lastModifiedAt` hoặc `computedScore` thường là thông tin thay đổi, không đại diện ID. Nếu đưa chúng vào, cùng entity có thể bị coi là một entity khác sau cập nhật. Công cụ Generate `equals()/hashCode()`, Lombok hoặc IDE chỉ viết code theo danh sách bạn chọn; chúng không tự biết mô hình nghiệp vụ.

### 6.2. ID chưa được cấp khi mới khởi tạo

Nếu database cấp `id` sau khi lưu, hai entity mới có `id == null`. Mẫu sau có thể khiến chúng bị xem là bằng nhau:

```java
// Minh họa lỗi khi id có thể cùng là null.
return Objects.equals(this.id, other.id);
```

Hơn nữa, nếu `hashCode()` dựa trực tiếp vào `id`, hash sẽ thay đổi khi ID được cấp. Cần quy định hành vi trước/sau persist. Một lựa chọn là cấp định danh bất biến khi tạo object (ví dụ UUID nếu hợp lý với hệ thống). Trong hệ thống dùng ID database, có thể xem hai entity chưa có ID chỉ bằng nhau khi cùng tham chiếu, đồng thời thiết kế hash ổn định và tránh đặt entity vào collection hash trước khi vòng đời khóa rõ ràng. Với JPA/Hibernate phải cân nhắc cả proxy, kiểu ID, session và equality của đối tượng detached. **Không có một công thức dùng ID được sinh sau lưu áp dụng an toàn cho mọi hệ thống.**

### 6.3. Dùng trường mutable trong key

Ví dụ `Person(name, address)` và `equals()/hashCode()` dùng `address`, sau đó đổi địa chỉ khi object đã trong `HashSet`. Hash cũ được dùng lúc insert và hash mới lúc tra cứu khác nhau, có thể khiến `contains(person)` là `false`. Nếu address chỉ là trạng thái người dùng chứ không tạo identity, bỏ nó khỏi key. Nếu address thật sự là một phần value object, xây mô hình immutable hoặc dùng key snapshot không thay đổi.

### 6.4. Chọn sai cách so sánh cho kiểu dữ liệu

- **Array:** `Objects.equals(a, b)` với array so sánh bản thân array (thường theo tham chiếu). Dùng `Arrays.equals()` cho nội dung một chiều, `Arrays.deepEquals()` khi cần so array lồng, và tính hash tương ứng bằng `Arrays.hashCode()` hoặc `Arrays.deepHashCode()`.
- **`BigDecimal`:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` do khác scale, dù `compareTo()` cho kết quả `0`. Nếu domain chỉ xét giá trị số, cần quy tắc chuẩn hóa thống nhất cả so sánh và hash; không trộn `compareTo() == 0` với hash thô của `BigDecimal`.
- **`double`/`float`:** dùng ngưỡng `Math.abs(a - b) < epsilon` để làm equality có thể vi phạm tính bắc cầu: A gần B, B gần C nhưng A không gần C. Nếu cần equality theo đơn vị làm tròn, hãy chuẩn hóa thành khóa giá trị theo một quy tắc được xác định trước.
- **Collection:** `List.equals()` có xét thứ tự, `Set.equals()` không dựa vào thứ tự phần tử, `Map.equals()` dựa vào cặp key-value. Nếu nghiệp vụ có ngữ nghĩa khác, phải biểu diễn hoặc chuẩn hóa đúng loại.
- **`null`:** `Objects.equals(x, y)` hữu ích cho trường nullable; nếu null không phải trạng thái hợp lệ, nên từ chối ở constructor thay vì âm thầm cho phép hai object thiếu khóa trở nên bằng nhau.

### 6.5. Dữ liệu chuẩn hóa không nhất quán

Với mã sản phẩm hay tên khóa, có thể cần bỏ khoảng trắng hoặc thống nhất chữ hoa/thường. Nhưng không tùy tiện dùng `toLowerCase()` cho mọi email, tên người, SKU hay mã kỹ thuật: tính phân biệt hoa/thường là quy tắc của domain. Nếu cần chuẩn hóa, làm **trước khi thiết lập khóa equality** và bảo đảm cả hash lẫn equality dựa trên cùng đại diện đã chuẩn hóa. Với chuỗi Unicode, loại bỏ dấu, biến đổi kiểu chữ hoặc normalization phải theo một chính sách cụ thể và được test bằng ca biên.

### 6.6. Kế thừa có thể phá đối xứng

Lớp cha kiểm tra `instanceof Parent` rồi chỉ so trường cha, còn lớp con kiểm tra thêm trường con, có thể khiến `parent.equals(child)` khác `child.equals(parent)`. Kiểm tra `getClass()` chặt hơn nhưng có thể khiến proxy/subclass không được coi là cùng loại, dù domain muốn vậy. Với value object, `final` hoặc `record` thường đơn giản hơn. Với hierarchy mở, phải xây hợp đồng bình đẳng thống nhất cho cả lớp cha và lớp con; gọi `super.equals()` không tự giải quyết mọi xung đột.

## 7. Mẫu triển khai khi có hai trường khóa

Giả sử một lớp `final MyKey` có hai trường `keyPartA` và `keyPartB` tạo thành khóa nghiệp vụ. **Đoạn mã sau chỉ là hai phương thức nằm bên trong lớp đã khai báo trường tương ứng, không phải chương trình độc lập:**

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof MyKey)) return false;
    MyKey that = (MyKey) other;
    return Objects.equals(keyPartA, that.keyPartA)
        && Objects.equals(keyPartB, that.keyPartB);
}

@Override
public int hashCode() {
    return Objects.hash(keyPartA, keyPartB);
}
```

`Objects.hash()` tiện lợi khi viết mã nhưng không bắt buộc; với đường đi chạy nóng, cân nhắc chi phí varargs/boxing nếu profiling cho thấy đáng kể. Quan trọng hơn hiệu năng vi mô là **chọn đúng trường**. Nếu các trường không cho phép null, constructor nên kiểm tra và thiết lập invariant rõ ràng. Đối với component là array hoặc collection mutable, cần quy tắc copy và hash tương ứng.

Nếu value object giữ `final List<String> tags`, việc trường là `final` chưa đủ để ngăn `tags.add(...)`. Có thể dùng `List.copyOf(tags)` trong constructor để khóa cấu trúc của list, nhưng đó là bản sao nông: nếu phần tử là object mutable thì vẫn cần chính sách riêng. Cũng đừng đưa trực tiếp collection thay đổi theo thời gian vào key nếu yêu cầu ổn định lâu dài.

## 8. Cách kiểm chứng lựa chọn bằng test

Sau khi chọn trường, nên tạo những cặp object có ý nghĩa nghiệp vụ cụ thể:

| Tình huống | Kỳ vọng |
| --- | --- |
| Cùng một tham chiếu | `equals()` là `true` |
| Khác instance nhưng cùng identity hợp lệ | `equals()` là `true` và hash bằng nhau |
| Cùng tên hiển thị nhưng khác định danh | `equals()` là `false` |
| Đổi trường trạng thái không quyết định identity | `equals()/hashCode()` không đổi |
| Hai value object khác một thành phần cốt lõi | `equals()` là `false` |
| So với `null` hoặc object kiểu không tương thích | `equals()` là `false` |
| Ba object được định nghĩa bằng nhau | Kiểm tra tính đối xứng và bắc cầu |
| Sử dụng làm key trong `HashMap`/`HashSet` | Tra cứu vẫn ổn định khi thay trường không thuộc key |

Một thư viện kiểm tra contract equality có thể phát hiện lỗi đối xứng, bắc cầu, hash mismatch. Tuy vậy, thư viện đó không thể tự biết domain muốn hai đối tượng nào là bằng nhau. Vì thế phải kiểm thử cả **ý nghĩa nghiệp vụ** lẫn **hợp đồng Java**.

## 9. Tự kiểm tra

**1.** `Product` có `productId` bất biến, `name`, `price` và `stockCount` có thể đổi. Nếu cùng ID nghĩa là cùng sản phẩm, nên chọn gì?  
**Đáp án:** `productId` (thêm namespace nếu ID chỉ duy nhất trong phạm vi đó). Các trường còn lại là trạng thái.

**2.** `Dimension(width, height, unit)` là value object; có thể bỏ `unit` khỏi equality không?  
**Đáp án:** Không mặc định. “10 cm” khác “10 m”; chỉ bỏ unit khi đã có chính sách quy đổi/chuẩn hóa nhất quán và giá trị được biểu diễn bằng một đơn vị chuẩn.

**3.** Hai object bằng nhau nhưng hash khác nhau có hợp lệ không?  
**Đáp án:** Không. Đây là vi phạm bắt buộc của `hashCode()`.

**4.** Hai object khác nhau có thể có cùng `hashCode()` không?  
**Đáp án:** Có. Collision không nói hai object bằng nhau.

**5.** Có nên đưa `updatedAt` vào equality của entity?  
**Đáp án:** Chỉ khi miền dữ liệu thật sự coi mỗi bản snapshot/phiên bản là một giá trị khác. Nếu cùng entity qua các lần cập nhật thì không.

**6.** `final List<String> tags` đã là khóa bất biến chưa?  
**Đáp án:** Chưa. Nội dung list vẫn có thể bị sửa. Cần copy phòng vệ hoặc chính sách immutable phù hợp.

**7.** `record` tự sinh equality có luôn khớp nghiệp vụ không?  
**Đáp án:** Không. Record mặc định dùng tất cả component; domain quyết định component nào mang ý nghĩa giá trị.

Điểm thực hành quan trọng nhất: **định nghĩa equality bằng luật của domain trước; chọn những trường thực sự đại diện giá trị/định danh; bảo đảm những trường đó ổn định và được dùng nhất quán bởi `equals()` cùng `hashCode()`.**