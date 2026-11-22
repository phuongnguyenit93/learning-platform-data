# Không dùng `toString()` để quyết định `equals()` hoặc `hashCode()`

## 1. Ba phương thức, ba trách nhiệm khác nhau

Mọi lớp Java đều thừa kế trực tiếp hoặc gián tiếp từ `java.lang.Object`. Ba phương thức `toString()`, `equals(Object)` và `hashCode()` có thể cùng xuất hiện trong một lớp, nhưng **không cùng phục vụ một mục đích**:

| Phương thức | Câu hỏi nó trả lời | Nơi thường sử dụng |
| --- | --- | --- |
| `toString()` | Làm sao biểu diễn đối tượng thành chuỗi dễ đọc? | Log, gỡ lỗi, hiển thị, chẩn đoán |
| `equals(Object)` | Khi nào hai đối tượng được coi là bằng nhau về logic? | So sánh giá trị, `contains`, `HashSet`, `HashMap` |
| `hashCode()` | Mã băm nào nhất quán với quan hệ bằng nhau của đối tượng? | Cấu trúc băm, `HashMap`, `HashSet` |

**Nguyên tắc:** `toString()` là cách **trình bày** một đối tượng. `equals()` và `hashCode()` xác định **hợp đồng bình đẳng và băm**. Không nên suy ra bình đẳng hoặc mã băm từ chuỗi dùng để trình bày.

Ví dụ, một tài khoản có `id = "A-100"`, `displayName = "Minh"`. Nếu hệ thống coi `id` là định danh thì hai tài khoản cùng tên hiển thị nhưng khác `id` **không bằng nhau**. Ngược lại, hai bản ghi cùng `id` nhưng tên hiển thị khác có thể được coi là cùng tài khoản logic. Việc `toString()` in thông tin gì không nên thay đổi những quy tắc này.

## 2. Hợp đồng thật sự của từng phương thức

### `Object.toString()`: biểu diễn chuỗi, không phải định danh

`Object.toString()` mặc định trả chuỗi gồm tên lớp, ký tự `@` và biểu diễn hex của mã băm do `hashCode()` trả về. Chẳng hạn một chuỗi có dạng minh họa:

```text
com.example.Customer@5e2de80c
```

Dãy hex trên **chỉ là ví dụ về định dạng**, không phải kết quả cố định; không có yêu cầu rằng hai object khác nhau luôn có chuỗi mặc định khác nhau. Mã băm cũng **không phải địa chỉ bộ nhớ hoặc ID duy nhất**. Một lớp có thể ghi đè `toString()` để trả bất kỳ mô tả phù hợp nào, chẳng hạn tên hiển thị, trạng thái tóm tắt hoặc các trường thuận tiện cho log.

API Java **không** quy định `toString()` mặc nhiên là biểu diễn chuẩn, bất biến, duy nhất, có thể phân tích ngược thành đối tượng, hoặc luôn phù hợp làm khóa dữ liệu. Khi đổi phiên bản ứng dụng, người phát triển có thể hợp lý thay đổi định dạng `toString()` nhằm cải thiện log.

### `Object.equals(Object)`: quy tắc bình đẳng về logic

`Object.equals(Object)` mặc định chỉ xem hai tham chiếu bằng nhau nếu chúng trỏ tới cùng object. Một lớp giá trị có thể ghi đè để so sánh các thành phần có ý nghĩa nghiệp vụ. Ví dụ `String.equals()` so nội dung chuỗi, còn một lớp `Customer` có thể so mã khách hàng.

Hợp đồng `equals` yêu cầu:

1. **Phản xạ:** `x.equals(x)` là `true` với `x` khác `null`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Bắc cầu:** nếu `x` bằng `y` và `y` bằng `z`, thì `x` bằng `z`.
4. **Nhất quán:** khi các thông tin liên quan không thay đổi, kết quả không thay đổi.
5. **Không bằng null:** `x.equals(null)` là `false`.

Ghi đè đúng chữ ký `public boolean equals(Object obj)` và nên đặt `@Override`. `equals(MyType)` chỉ là một overload trong trường hợp thông thường, không thay thế hợp đồng của `Object.equals(Object)`.

### `Object.hashCode()`: phải khớp với equals

Quy tắc bắt buộc:

```text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
```

Chiều ngược lại không bắt buộc: hai đối tượng có cùng hash vẫn có thể không bằng nhau (va chạm hash). Với những trường dùng trong `equals` không đổi, `hashCode` cũng cần ổn định trong một lần chạy của ứng dụng.

**Không có quy tắc nào yêu cầu `toString()` của hai đối tượng bằng nhau phải giống nhau.** Việc đưa `toString()` vào `equals/hashCode` có nguy cơ vô tình biến thay đổi hiển thị thành thay đổi định danh.

## 3. Vì sao so sánh `toString()` dễ sai?

Giả sử `User.toString()` chỉ hiển thị tên người dùng. Hai tài khoản riêng biệt cùng tên `"An"` có thể cho **chuỗi giống hệt nhau**. Nếu viết:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof User other
            && toString().equals(other.toString());
}
```

Đây là **đoạn minh họa đặt trong lớp `User`**, không phải chương trình độc lập. Lỗi không nằm ở cú pháp so chuỗi: lỗi là **chuỗi hiển thị không thể hiện chính xác danh tính theo nghiệp vụ**.

Các nguyên nhân phổ biến:

- **Thiếu thông tin:** `toString()` chỉ in tên, một vài trường hoặc tóm tắt. Hai object khác nhau có thể có cùng chuỗi.
- **Thừa thông tin:** `toString()` in thời gian cập nhật, cache, debug flag hoặc trạng thái tạm thời dù những dữ liệu đó không tham gia bình đẳng.
- **Định dạng thay đổi:** thêm tiền tố, dấu phân cách, đổi thứ tự trường, bản địa hóa ngày/giờ hoặc che bớt dữ liệu nhạy cảm có thể đổi chuỗi mà không đổi giá trị logic.
- **Không có bảo đảm duy nhất:** hai object không bằng nhau không buộc phải có hai `toString()` khác nhau; hai object bằng nhau cũng không buộc phải có chuỗi giống nhau.
- **Tốn tài nguyên hoặc phát sinh side effect:** một implementation `toString()` có thể duyệt cấu trúc lớn, gọi phương thức khác, thậm chí bị ảnh hưởng bởi trạng thái bên ngoài. Mã băm cần được thiết kế theo trạng thái dùng làm equality, không theo công việc trình bày.

Ngay cả khi `toString()` tình cờ chứa đủ trường ở phiên bản hiện tại, lần refactor chỉ nhằm đổi cách log có thể phá logic tìm kiếm và so sánh. Đây là kiểu phụ thuộc khó nhận ra trong code review.

## 4. Ví dụ Java 17+: dùng toString dẫn đến nhầm tài khoản

Tạo tệp `BadToStringEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BadToStringEqualityDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;

        Account(String accountId, String displayName) {
            this.accountId = accountId;
            this.displayName = displayName;
        }

        @Override
        public String toString() {
            return displayName; // Chỉ để hiển thị.
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Account other
                    && toString().equals(other.toString()); // Sai về nghiệp vụ.
        }

        @Override
        public int hashCode() {
            return toString().hashCode(); // Phụ thuộc chuỗi hiển thị.
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A-100", "Minh");
        Account b = new Account("B-200", "Minh");
        Account c = new Account("A-100", "Minh mới");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));

        Set<Account> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(c);
        System.out.println(unique.size());

        Map<Account, String> balances = new HashMap<>();
        balances.put(a, "old");
        balances.put(b, "new");
        System.out.println(balances.size());
        System.out.println(balances.get(a));
    }
}
```

Biên dịch và chạy:

```bash
javac BadToStringEqualityDemo.java
java BadToStringEqualityDemo
```

Kết quả:

```text
true
false
2
1
new
```

**Giải thích:**

1. `a` và `b` khác mã tài khoản nhưng đều in `"Minh"`. `equals` sai trả `true`; `HashSet` xem chúng là một phần tử và `HashMap` xem là một khóa.
2. `a` và `c` cùng mã `"A-100"` nhưng tên hiển thị khác, nên `equals` sai trả `false`.
3. Set còn hai phần tử vì nó gộp `a` với `b` nhưng giữ `c`. Với map, `put(b, "new")` thay thế giá trị gắn với khóa logic `a`, vì thế `get(a)` trả `"new"`.

Lưu ý về tính chính xác: implementation này **vẫn có thể đáp ứng các định luật hình thức** của `equals` trong tình huống tên hiển thị bất biến, vì nó so `String` và băm theo `String`. Điều sai là **định nghĩa bình đẳng không khớp yêu cầu nghiệp vụ**: mã tài khoản bị bỏ qua. Không phải cứ `equals(toString())` là tự động vi phạm tính đối xứng hoặc bắc cầu; lỗi là chọn nhầm nguồn dữ liệu và làm hợp đồng phụ thuộc cách hiển thị.

## 5. Cách đúng: so sánh trường tạo nên danh tính và băm từ cùng trường đó

Nếu tài khoản được nhận dạng bằng `accountId`, hãy dùng chính trường này trong `equals` và `hashCode`. `toString` được phép hiển thị tên, mã, hoặc một tóm tắt khác độc lập với equality.

Tạo tệp `GoodAccountEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class GoodAccountEqualityDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;

        Account(String accountId, String displayName) {
            this.accountId = Objects.requireNonNull(accountId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Account other)) {
                return false;
            }
            return accountId.equals(other.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }

        @Override
        public String toString() {
            return "Account{id=" + accountId
                    + ", displayName=" + displayName + "}";
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A-100", "Minh");
        Account b = new Account("B-200", "Minh");
        Account c = new Account("A-100", "Minh mới");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.toString().equals(c.toString()));

        Set<Account> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(c);
        System.out.println(unique.size());

        Map<Account, String> balances = new HashMap<>();
        balances.put(a, "old");
        balances.put(c, "updated");
        System.out.println(balances.size());
        System.out.println(balances.get(a));
    }
}
```

Lệnh chạy:

```bash
javac GoodAccountEqualityDemo.java
java GoodAccountEqualityDemo
```

Kết quả:

```text
false
true
false
2
1
updated
```

Ở phiên bản đúng:

- `a` và `b` cùng tên nhưng khác `accountId`, vì vậy `equals` trả `false`.
- `a` và `c` cùng `accountId` nên `equals` trả `true`, mặc dù `toString()` khác nhau vì tên hiển thị khác.
- `hashCode` chỉ dựa vào `accountId`, đúng với cách định nghĩa equality; hai object bằng nhau có cùng hash.
- `HashSet` giữ hai tài khoản logic `A-100` và `B-200`. `HashMap` dùng `a` và `c` như cùng khóa logic và cập nhật giá trị thành `"updated"`.

`Account` trong ví dụ là lớp `final`, `accountId` là `final`, và `String` bất biến. Điều này giúp mã băm ổn định khi object nằm trong một tập hợp hoặc làm khóa map. Việc chọn một trường duy nhất làm danh tính là **giả thiết nghiệp vụ của ví dụ**; trong ứng dụng thật, hãy xác định khóa tự nhiên, khóa tổng hợp hoặc toàn bộ trường giá trị phù hợp.

## 6. Một vòng phụ thuộc dễ gây StackOverflowError

Một rủi ro riêng xuất hiện khi lập trình viên dùng `toString()` để tính `hashCode()`, rồi lại dùng `hashCode()` trong `toString()`:

```java
@Override
public String toString() {
    return "Node#" + hashCode();
}

@Override
public int hashCode() {
    return toString().hashCode();
}
```

Đây là **đoạn mã lỗi minh họa trong một lớp `Node`**, không phải chương trình độc lập. `hashCode()` gọi `toString()`, rồi `toString()` lại gọi `hashCode()` không có điều kiện dừng. Khi được thực thi, đệ quy sẽ dẫn tới `StackOverflowError` thay vì mã băm có ích.

Ngay cả `Object.toString()` mặc định cũng liên quan `hashCode()` trong biểu diễn hex, nên không thể coi việc chuyển đổi object thành chuỗi là một thao tác trung lập để định nghĩa lại `hashCode`. Cần tách các phương thức theo chức năng ngay từ thiết kế.

## 7. Khi toString thay đổi hoặc trạng thái hiển thị có thể thay đổi

Giả sử một đối tượng giữ mã khách hàng bất biến nhưng tên hiển thị có thể được chỉnh sửa. Nếu `hashCode()` tính từ `toString()` có chứa tên, sau khi chỉnh tên:

1. Object đang nằm trong nhóm băm cũ ở `HashSet` hoặc `HashMap`.
2. Lời gọi `hashCode()` mới có thể trả số khác.
3. `contains`, `remove` hoặc `get` có thể tìm ở nhóm mới và không gặp object đã lưu.

Trường hợp này gây khó tìm lỗi vì object vẫn tồn tại trong collection nhưng tra cứu không hoạt động như kỳ vọng.

**Cách phòng tránh:** dùng trạng thái bất biến và ổn định cho các trường tham gia equality/hash. Nếu buộc phải thay khóa logic, xóa phần tử hoặc mục map **trước khi thay trạng thái**, rồi cập nhật và thêm lại; hoặc tạo một đối tượng khóa bất biến mới.

Một thay đổi hoàn toàn vô hại ở tầng trình bày, chẳng hạn chuyển `toString()` từ `"A-100"` sang `"Account A-100"`, không được phép làm thay đổi danh tính hoặc mã băm của object trong thiết kế đúng.

## 8. Còn trường hợp chuỗi là chính giá trị nghiệp vụ thì sao?

Không phải lúc nào việc dùng dữ liệu dạng chuỗi cũng sai. **Nếu định danh nghiệp vụ thực sự là một chuỗi**, ví dụ `accountId` hoặc một mã chuẩn hóa, hãy so sánh trực tiếp **trường chuỗi định danh**:

```java
return accountId.equals(other.accountId);
```

và dùng:

```java
return accountId.hashCode();
```

Hai đoạn trên minh họa thân phương thức trong lớp `Account` đã kiểm tra kiểu `other`, không phải chương trình độc lập.

Nếu thiết kế một kiểu bao bọc chuỗi đã chuẩn hóa, hãy biểu diễn quy tắc chuẩn hóa bằng một thành phần hoặc phương thức có tên rõ ràng (ví dụ `normalizedKey()`), và bảo đảm `equals/hashCode` luôn áp dụng cùng tiêu chí đó. Đừng sử dụng `toString()` làm một “đường tắt” bởi vì ý nghĩa thường thấy của nó chỉ là **hiển thị**.

Tương tự, chuỗi JSON, XML hoặc CSV dùng để trao đổi dữ liệu nên được tạo bởi một **serializer có định dạng và phiên bản được quy định**, thay vì coi `toString()` mặc nhiên là biểu diễn dữ liệu chuẩn. Nếu cần cache key ổn định, hãy tạo khóa từ dữ liệu đã chuẩn hóa theo schema rõ ràng. Những cân nhắc này giữ tách biệt với hợp đồng đối tượng mà `equals/hashCode` đang bảo đảm.

## 9. Java record giúp gì và cần lưu ý gì?

Với kiểu dữ liệu giá trị đơn giản, Java 17 `record` tự sinh `equals(Object)` và `hashCode()` theo các thành phần record.

```java
record Coordinate(int x, int y) {}
```

Đây là khai báo kiểu độc lập có thể đặt ở phạm vi top-level trong tệp `Coordinate.java`. Hai `Coordinate(1, 2)` có cùng giá trị thành phần sẽ bằng nhau và có mã băm tương thích, dù không phải cùng object. Java cũng cung cấp `toString()` mô tả thành phần, nhưng **không dùng chuỗi ấy làm cơ sở cho equality**.

Nếu một thành phần record là danh sách hoặc object mutable, record chỉ giữ **tham chiếu** ở trường `final`; nó không tự tạo bất biến sâu. Người dùng vẫn cần bảo đảm dữ liệu tham gia equality không bị sửa khi record đang làm khóa trong cấu trúc băm.

Một lưu ý khác: nếu danh tính nghiệp vụ chỉ dựa vào mã `id`, trong khi record còn chứa `displayName`, việc tự sinh equality theo **mọi thành phần** có thể không khớp. Khi đó hãy thiết kế lại mô hình dữ liệu, một value object chỉ chứa khóa định danh, hoặc tự định nghĩa equality theo hợp đồng nghiệp vụ.

## 10. Những nhầm lẫn cần tránh

| Nhầm lẫn | Sự thật và cách xử lý |
| --- | --- |
| “Hai `toString()` giống nhau thì hai object bằng nhau.” | Chuỗi hiển thị có thể bỏ qua thông tin phân biệt; dùng `equals` được định nghĩa đúng. |
| “Hai object bằng nhau phải có `toString()` giống nhau.” | Không có yêu cầu này trong hợp đồng `Object.equals`; có thể khác chi tiết hiển thị. |
| “Chỉ cần hash giống nhau là cùng object.” | Hash collision hợp lệ; `equals` mới quyết định equality. |
| “`Object.toString()` cho ID duy nhất của object.” | Biểu diễn mặc định dựa trên hash, không bảo đảm duy nhất hay ổn định ngoài hợp đồng. |
| “Dùng `toString()` làm hash dễ bảo trì.” | Thay đổi format hiển thị có thể làm thay đổi hash; băm từ trường tham gia `equals`. |
| “Có `equals(MyType)` là đủ để HashMap dùng.” | Đó thường là overload; phải override đúng `equals(Object)`. |
| “Record làm mọi dữ liệu bên trong bất biến.” | Record không tự làm bất biến sâu các object mutable được tham chiếu. |
| “Tên hiển thị bằng nhau tức là cùng thực thể.” | Điều này phụ thuộc định nghĩa danh tính nghiệp vụ; thường cần ID ổn định. |

## 11. Checklist khi thiết kế object contract

1. **Định nghĩa danh tính hoặc giá trị logic** của kiểu trước: trường nào quyết định hai object bằng nhau?
2. **Ghi đè `equals(Object)`** theo chính các trường đó; xử lý `null`, kiểu không phù hợp và các điều kiện đối xứng/bắc cầu.
3. **Ghi đè `hashCode()`** theo cùng trường tham gia `equals`; hai object bằng nhau phải cùng mã băm.
4. **Viết `toString()` cho người đọc**: đủ hữu ích để gỡ lỗi, tránh lộ bí mật, nhưng không dùng nó làm nguồn truth cho identity/equality.
5. **Ưu tiên trường bất biến** cho identity/hash, nhất là khi object là khóa của `HashMap` hoặc phần tử `HashSet`.
6. **Kiểm thử độc lập ba phương thức**: hai object cùng ID nhưng khác tên hiển thị; hai object khác ID nhưng cùng tên; thay đổi format `toString()` không được thay đổi `equals/hashCode`.
7. **Kiểm thử qua collection**: `HashSet.add`, `HashMap.put/get` phải khử trùng hoặc cập nhật theo danh tính nghiệp vụ, không theo chuỗi hiển thị.
8. **Tránh vòng gọi đệ quy** giữa `toString`, `hashCode` và các phương thức mà chúng phụ thuộc.
9. **Nếu cần biểu diễn chuẩn**, tạo serializer hoặc `canonicalKey()` có hợp đồng riêng và kiểm thử ổn định định dạng; không lẫn với phương thức `toString` phục vụ chẩn đoán.

**Tự kiểm tra:**

- Hai tài khoản khác ID nhưng cùng tên hiển thị có bắt buộc bằng nhau không? **Không.**
- Hai tài khoản cùng ID nhưng format `toString()` khác nhau có thể bằng nhau không? **Có**, nếu ID là tiêu chí equality.
- Việc đổi nội dung log trong `toString()` có được làm đổi `hashCode()` không? **Không**, khi những trường tham gia equality không thay đổi.
- Khi nào `hashCode()` phải giống nhau giữa hai object? **Khi `equals()` của chúng là `true`.**
- Muốn khóa chuỗi chuẩn cho cache thì dùng `toString()` tùy ý hay tạo `canonicalKey()` rõ hợp đồng? **Tạo khóa chuẩn có định nghĩa và kiểm thử riêng.**

**Ghi nhớ:** `toString()` trả lời “đối tượng trông như thế nào khi in ra”; `equals()` và `hashCode()` trả lời “đối tượng nào là cùng một giá trị logic”. Hãy xây equality/hash từ những thành phần nghiệp vụ ổn định, để thay đổi giao diện hoặc log không bao giờ âm thầm làm thay đổi hợp đồng của object.