# So sánh có xét null bằng Objects.equals trong Java

**Chủ đề:** Java 7 — `Objects`  
**Bài học:** So sánh có xét `null` bằng `Objects.equals`  
**Phạm vi:** Java 17+; API `java.util.Objects.equals(Object, Object)` được giới thiệu từ Java 7 và vẫn được sử dụng trong Java hiện đại. Bài tập trung vào **equality null-safe**, hợp đồng `equals`/`hashCode` và lựa chọn phương thức đúng cho từng cấu trúc dữ liệu.

## 1. Vấn đề: gọi equals() trên tham chiếu có thể null

Với hai đối tượng `left` và `right`, ta thường muốn so sánh **giá trị** thay vì kiểm tra hai biến có trỏ tới **cùng một đối tượng** không.

Cách gọi quen thuộc:

```java
boolean same = left.equals(right);
```

Đây là **đoạn minh họa trong một phương thức**. Nếu `left == null`, lời gọi trên sẽ ném `NullPointerException` trước khi có thể quyết định hai giá trị có bằng nhau hay không.

Có thể viết thủ công:

```java
boolean same = left == right
        || (left != null && left.equals(right));
```

Hoặc sử dụng API có sẵn:

```java
boolean same = java.util.Objects.equals(left, right);
```

**`Objects.equals(a, b)` xử lý cả hai đối số null theo quy tắc xác định.** Đây là điểm khác với `a.equals(b)` khi `a` có thể null. Tuy nhiên, null-safe **không có nghĩa** nó biết cách diễn giải bình đẳng theo mọi quy tắc nghiệp vụ, tự ép kiểu số, so sánh sâu mảng hay sửa một implementation `equals` sai hợp đồng.

### 1.1. Import và chữ ký

```java
import java.util.Objects;

// Chữ ký API:
// public static boolean equals(Object a, Object b)
```

`Objects` là **utility class** trong `java.util`. `equals` là phương thức `static`, không cần khởi tạo `new Objects()`. Có thể gọi `Objects.equals(a, b)` hoặc `java.util.Objects.equals(a, b)` khi không muốn import.

## 2. Quy tắc chính xác của Objects.equals

Về mặt ngữ nghĩa, phép so sánh tương đương với:

```java
return a == b || (a != null && a.equals(b));
```

Đây là **biểu thức minh họa** cho logic, không phải method độc lập. Ba trường hợp nền tảng:

1. Nếu `a` và `b` cùng là `null`, kết quả **`true`**.
2. Nếu chỉ một đối số là `null`, kết quả **`false`** đối với các implementation `equals` tuân thủ hợp đồng.
3. Nếu hai tham chiếu không cùng trỏ một đối tượng và `a` khác null, kết quả do **`a.equals(b)`** quyết định.

Có một điều cần nói chính xác: nếu `a` khác null, `b` null, lời gọi `a.equals(null)` vẫn được thực thi. Hợp đồng `Object.equals` quy định `x.equals(null)` phải trả `false`, nhưng **một implementation tùy chỉnh làm sai hợp đồng có thể ném exception**. `Objects.equals` không bọc mọi ngoại lệ từ `equals` của người viết class.

### 2.1. Bảng kết quả

| `a` | `b` | `Objects.equals(a, b)` | Lý do |
| --- | --- | --- | --- |
| `null` | `null` | `true` | Cả hai cùng tham chiếu null |
| `null` | `"java"` | `false` | Chỉ một đối số null |
| `"java"` | `null` | `false` | `String.equals(null)` trả false |
| `"java"` | `new String("java")` | `true` | Nội dung String giống nhau |
| Hai biến giữ cùng một object | Cùng object | `true` | Nhánh so sánh tham chiếu |
| Hai object riêng có `equals` theo giá trị | Giá trị bằng nhau | `true` nếu `equals` trả true | Phụ thuộc hợp đồng của class |
| Hai object riêng không override `equals` | Hai instance khác nhau | Thường `false` | Kế thừa `Object.equals` theo identity |

**Hai giá trị null được coi bằng nhau** là quy tắc của API, không phải kết luận “hai trường nghiệp vụ cùng bị thiếu dữ liệu là hợp lệ”. Nếu nghiệp vụ cần ít nhất một giá trị thật, phải **thêm điều kiện khác null**.

### 2.2. Ví dụ độc lập: null, identity và equality

Tạo tệp `NullSafeEqualsDemo.java`:

```java
import java.util.Objects;

public class NullSafeEqualsDemo {
    public static void main(String[] args) {
        String left = new String("java");
        String right = new String("java");

        System.out.println(
                "both-null=" + Objects.equals(null, null));
        System.out.println(
                "left-null=" + Objects.equals(null, left));
        System.out.println(
                "right-null=" + Objects.equals(left, null));
        System.out.println(
                "same-reference=" + (left == right));
        System.out.println(
                "same-value=" + Objects.equals(left, right));
        System.out.println(
                "different-number-types="
                + Objects.equals(10, 10L));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all NullSafeEqualsDemo.java
java NullSafeEqualsDemo
```

**stdout chính xác:**

```text
both-null=true
left-null=false
right-null=false
same-reference=false
same-value=true
different-number-types=false
```

Hai lời gọi `new String("java")` tạo hai object khác nhau, nên `left == right` là false; `String.equals` so sánh nội dung nên `Objects.equals(left, right)` là true.

`Objects.equals(10, 10L)` là false do hai primitive được **boxing** thành `Integer` và `Long`. Hai kiểu wrapper không được tự động quy đổi sang một kiểu số thống nhất bên trong `Objects.equals`.

## 3. So với toán tử == và gọi equals() trực tiếp

Ba dạng kiểm tra phục vụ các mục đích khác nhau:

| Biểu thức | Với reference có null | So sánh cái gì? | Khi nên dùng |
| --- | --- | --- | --- |
| `a == b` | Không ném lỗi chỉ vì null | **Cùng tham chiếu** đối với reference; giá trị đối với primitive | Identity, so sánh null, enum bằng `==` |
| `a.equals(b)` | Có thể ném `NullPointerException` nếu `a` null | Theo `equals` do class khai báo | Khi biết chắc `a` khác null và cần equality |
| `Objects.equals(a, b)` | Xử lý null có chủ đích | Identity trước, sau đó `a.equals(b)` | Khi một hoặc cả hai reference có thể null |
| `"ACTIVE".equals(status)` | An toàn nếu `status` null | String content equality | Khi có một hằng String chắc chắn khác null |
| `Objects.deepEquals(a,b)` | Có xét null | Có xử lý sâu khi hai đối tượng là arrays | Khi so sánh cấu trúc mảng phù hợp |

**Ví dụ `String`:** dùng `==` để so sánh nội dung chuỗi là lỗi thiết kế dù các chuỗi literal được intern có thể tình cờ trả true. Với enum, `==` lại là lựa chọn thường dùng, rõ nghĩa và null-safe đối với hai biến enum reference.

**Ví dụ nullable primitive wrappers:** `Integer x` có thể null; một lời so sánh số bằng `x == 10` có thể thực hiện **unboxing** và ném `NullPointerException` nếu `x` null. `Objects.equals(x, 10)` không gây unboxing cho phép so sánh đó, nhưng nó trả false khi `x` null; không nên dùng nó thay phép tính số học.

### 3.1. Tại sao Objects.equals không có “hai chiều” riêng?

Khi `a != b` và `a != null`, phương thức **chỉ gọi `a.equals(b)`**. Nó không thực hiện thêm `b.equals(a)` để kiểm tra đối xứng.

Nếu một class cài `equals` sai, bạn có thể gặp tình huống:

```java
// Ví dụ có vấn đề về thiết kế:
// Objects.equals(a, b) != Objects.equals(b, a)
```

Đây là **đoạn minh họa một bất biến bị vi phạm**, không phải tình huống nên xây dựng trong production. Nguyên nhân nằm ở **hợp đồng equals không đối xứng**, chứ không phải `Objects.equals` có nhiệm vụ sửa lỗi cho class đó. Khi thấy phép so sánh thay đổi theo thứ tự hai tham số, hãy sửa `equals` của loại dữ liệu liên quan.

## 4. Hợp đồng Object.equals quyết định kết quả

`Objects.equals` là wrapper null-safe của một phép so sánh **theo hợp đồng equals của các class liên quan**. Muốn dùng đúng, phải biết hợp đồng cơ bản của `Object.equals`:

1. **Reflexive:** với `x` khác null, `x.equals(x)` là true.
2. **Symmetric:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Transitive:** nếu `x` bằng `y`, `y` bằng `z` thì `x` bằng `z`.
4. **Consistent:** khi dữ liệu tham gia equality không thay đổi, nhiều lần gọi cho cùng kết quả.
5. **Non-nullity:** `x.equals(null)` phải false khi `x` khác null.

**Liên hệ với hashCode:** nếu `x.equals(y)` là true, bắt buộc `x.hashCode() == y.hashCode()`. Chiều ngược lại **không bắt buộc**: hai object khác nhau có thể cùng hash code (hash collision).

Nếu chỉ override `equals` mà không override `hashCode` nhất quán, code dùng `HashSet`, `HashMap` hoặc các cấu trúc dựa trên hashing có thể hành xử không đúng kỳ vọng, dù `Objects.equals` trả true.

### 4.1. Không override equals thì mặc định so sánh identity

Một class bình thường không override `equals` kế thừa implementation `Object.equals`, so sánh theo tham chiếu. Hai instance có field giống hệt nhau **không tự động bằng nhau**.

`Objects.equals` không tự duyệt từng field và không thực hiện reflection để “đoán” giá trị nào quan trọng. Muốn equality dựa trên các field, class phải triển khai `equals` (và `hashCode`) hoặc sử dụng một kiểu có value semantics phù hợp như `record` từ Java 16+.

## 5. Thiết kế equals/hashCode dùng Objects.equals cho field có thể null

Đây là một ứng dụng quan trọng của `Objects.equals`: cài `equals` cho một immutable value class có field nullable mà không cần nhiều nhánh `if`.

Tạo tệp `UserKeyEqualityDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class UserKeyEqualityDemo {
    static final class UserKey {
        private final String tenant;
        private final String externalId;

        UserKey(String tenant, String externalId) {
            this.tenant = tenant;
            this.externalId = externalId;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof UserKey key)) {
                return false;
            }
            return Objects.equals(tenant, key.tenant)
                    && Objects.equals(externalId, key.externalId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, externalId);
        }
    }

    public static void main(String[] args) {
        UserKey a = new UserKey("tenant-a", "user-7");
        UserKey b = new UserKey("tenant-a", "user-7");
        Set<UserKey> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);

        System.out.println(
                "equal=" + Objects.equals(a, b));
        System.out.println(
                "hash-equal=" + (a.hashCode() == b.hashCode()));
        System.out.println(
                "set-size=" + unique.size());
        System.out.println(
                "null-field-equal="
                + Objects.equals(
                    new UserKey("tenant-a", null),
                    new UserKey("tenant-a", null)));
        System.out.println(
                "different="
                + Objects.equals(a,
                    new UserKey("tenant-b", "user-7")));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all UserKeyEqualityDemo.java
java UserKeyEqualityDemo
```

```text
equal=true
hash-equal=true
set-size=1
null-field-equal=true
different=false
```

**Giải thích quan trọng:**

- `UserKey` là `final` nên không có subclass tự thay đổi quy tắc equality và gây bất đối xứng không mong muốn. Tất nhiên vẫn phải bảo đảm các field được chọn phản ánh đúng identity nghiệp vụ.
- `this == other` xử lý nhanh trường hợp cùng instance. Với các instance khác, `instanceof UserKey key` xác thực kiểu rồi tạo biến mẫu kiểu `UserKey` (pattern matching for `instanceof` chính thức từ Java 16).
- `Objects.equals(tenant, key.tenant)` và `Objects.equals(externalId, key.externalId)` so sánh từng field ngay cả khi cả hai có thể null.
- `hashCode()` sử dụng `Objects.hash(tenant, externalId)` với cùng tập field tham gia `equals`. Đây là cách viết gọn; với code hiệu năng cực cao, có thể cân nhắc chi phí tạo varargs array của `Objects.hash` rồi đo bằng benchmark thực tế.
- `HashSet` chỉ giữ một key cho hai đối tượng cùng nội dung. `set-size=1` thể hiện `equals/hashCode` nhất quán.
- Vì `Objects.equals(null, null)` trả true, **hai field `externalId` cùng null được coi bằng nhau** trong thiết kế này. Nếu nghiệp vụ không cho thiếu ID, hãy validate constructor (ví dụ `Objects.requireNonNull(externalId)`) thay vì mặc nhiên chấp nhận hai giá trị thiếu.

**Một ràng buộc quan trọng:** đừng đưa field mutable có thể thay đổi sau khi object trở thành khóa của `HashMap`/phần tử `HashSet` vào `equals/hashCode` mà không cân nhắc. Nếu hash code thay đổi trong khi object đang nằm trong hash-based collection, phép tra cứu/xóa có thể thất bại. Immutable value objects là lựa chọn dễ kiểm chứng hơn.

### 5.1. Phân biệt Objects.hash và Objects.hashCode

- `Objects.hash(a, b)` tổng hợp hash từ **nhiều giá trị** qua varargs, hữu ích khi viết `hashCode` cho một object.
- `Objects.hashCode(x)` lấy hash code của **một** object, trả 0 khi `x` null.
- `Objects.hash(x)` với chỉ một đối số **không được bảo đảm bằng** `Objects.hashCode(x)`: nó tính hash cho một chuỗi varargs một phần tử theo `Arrays.hashCode(Object[])`. Đừng tùy tiện thay hai cách viết này cho nhau nếu contract cần nhất quán.

Dù chọn cách nào, **chính tập field** dùng để quyết định equality phải phù hợp với cách tính hash code. Một kết quả hash bằng nhau **không có nghĩa** hai object bằng nhau.

## 6. Record trên Java hiện đại: tự có equality theo component

Từ Java 16, `record` cung cấp một cách khai báo **data carrier** với các method được tạo tự động, bao gồm `equals`, `hashCode` và `toString`. Với những kiểu dùng làm key/value đơn giản, nó có thể tránh phải viết boilerplate thủ công.

Ví dụ:

```java
record OrderLine(String sku, int quantity) {}
```

Đây là **khai báo kiểu minh họa**. Hai `OrderLine` riêng biệt có cùng giá trị các record component sẽ so sánh bằng nhau. `Objects.equals(order1, order2)` vì vậy cũng trả true khi component equality phù hợp.

**Nhưng record không tự tạo deep equality cho mảng.** Nếu một component có kiểu `byte[]`, record equality của component mảng vẫn theo phép so sánh mảng mang ngữ nghĩa reference, trừ khi chính bạn thiết kế lại hợp đồng. Và record không tự deep-copy đối tượng mutable trong component.

### 6.1. Ví dụ record kết hợp BigDecimal

Tạo `RecordAndMoneyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class RecordAndMoneyDemo {
    record Line(String sku, int quantity) {}
    record Bytes(byte[] data) {}

    public static void main(String[] args) {
        Line a = new Line("A", 2);
        Line b = new Line("A", 2);
        System.out.println("record=" + Objects.equals(a, b));

        Bytes x = new Bytes(new byte[] {1, 2});
        Bytes y = new Bytes(new byte[] {1, 2});
        System.out.println(
                "record-with-array=" + Objects.equals(x, y));

        BigDecimal p = new BigDecimal("1.0");
        BigDecimal q = new BigDecimal("1.00");
        System.out.println(
                "decimal-equals=" + Objects.equals(p, q));
        System.out.println(
                "decimal-numeric="
                + (p.compareTo(q) == 0));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RecordAndMoneyDemo.java
java RecordAndMoneyDemo
```

```text
record=true
record-with-array=false
decimal-equals=false
decimal-numeric=true
```

**Hai ví dụ quan trọng về khác biệt ngữ nghĩa:**

- `Line` có component là `String` và primitive `int`. Equality được tạo tự động nên hai record có dữ liệu tương đương trả true.
- `Bytes` có array component. Hai mảng `new byte[]{1,2}` khác instance, nên hai record này không bằng nhau dù bytes giống nhau. Nếu cần value equality cho payload nhị phân, hãy viết logic so sánh bằng `Arrays.equals` và xây dựng bất biến/copy phòng vệ thích hợp.
- `BigDecimal.equals` so sánh **giá trị lẫn scale**; `1.0` và `1.00` có scale khác nhau, vì thế `Objects.equals(p,q)` trả false. `compareTo` xác định chúng bằng nhau **về giá trị số**. Chọn chuẩn hóa/cách so sánh phù hợp yêu cầu nghiệp vụ tiền tệ, chứ không coi một API mặc nhiên đúng cho mọi mô hình.

**Cảnh báo hợp đồng:** `BigDecimal.compareTo` có thể cho ra 0 ở hai object mà `equals` trả false. Vì vậy dùng một tiêu chí tùy chỉnh kiểu `compareTo==0` để định nghĩa key equality trong hash collections cần thiết kế lại hash tương ứng; không tự thay `equals` bằng `compareTo` ở mọi nơi.

## 7. Mảng: Objects.equals không so sánh nội dung

Mảng Java **không override `Object.equals` để so sánh từng phần tử**. Vì vậy:

```java
int[] a = {1, 2};
int[] b = {1, 2};
boolean same = java.util.Objects.equals(a, b);
```

Đây là **đoạn minh họa** trong method; `same` là false do `a` và `b` là hai mảng khác nhau.

Chọn phương thức theo dữ liệu:

| Mục tiêu | API phù hợp |
| --- | --- |
| Hai reference mảng có phải cùng mảng? | `a == b` hoặc `Objects.equals(a,b)` |
| Nội dung mảng primitive một chiều có bằng nhau? | `Arrays.equals(int[], int[])` hoặc overload tương ứng |
| Nội dung `Object[]` một chiều có bằng nhau? | `Arrays.equals(Object[], Object[])`, dùng `Objects.equals` cho từng phần tử |
| Nội dung mảng lồng nhau, gồm mảng primitive ở các tầng sâu | `Arrays.deepEquals(Object[], Object[])` / `Objects.deepEquals(a,b)` theo loại đối số |
| Hai đối tượng bất kỳ có thể null, nếu là mảng cần so sánh sâu | `Objects.deepEquals(a,b)`, nhưng hiểu giới hạn và ngữ nghĩa dữ liệu |

`Objects.deepEquals` là API khác `Objects.equals`. Nó dùng xử lý sâu khi cả hai đối số là arrays phù hợp; đối với object không phải array, nó sử dụng `equals` thông thường. Cũng giống như các API equality khác, việc so sánh sâu **không tự hiểu mọi loại container tùy biến**.

### 7.1. Ví dụ độc lập cho arrays và collections

Tạo `ArraysAndCollectionsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ArraysAndCollectionsDemo {
    public static void main(String[] args) {
        int[] first = {1, 2};
        int[] second = {1, 2};

        System.out.println(
                "objects-array="
                + Objects.equals(first, second));
        System.out.println(
                "arrays-content="
                + Arrays.equals(first, second));
        System.out.println(
                "deep-primitive="
                + Objects.deepEquals(first, second));

        Object[] nestedA = {
            new int[] {1, 2},
            new String[] {"x", "y"}
        };
        Object[] nestedB = {
            new int[] {1, 2},
            new String[] {"x", "y"}
        };
        System.out.println(
                "nested-deep="
                + Objects.deepEquals(nestedA, nestedB));

        System.out.println(
                "list-content="
                + Objects.equals(
                    List.of("a", "b"),
                    List.of("a", "b")));
        System.out.println(
                "list-of-arrays="
                + Objects.equals(
                    List.of(new int[] {1, 2}),
                    List.of(new int[] {1, 2})));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ArraysAndCollectionsDemo.java
java ArraysAndCollectionsDemo
```

```text
objects-array=false
arrays-content=true
deep-primitive=true
nested-deep=true
list-content=true
list-of-arrays=false
```

**Đọc kết quả:**

1. `Objects.equals(first, second)` là false do hai mảng primitive khác identity.
2. `Arrays.equals` và `Objects.deepEquals` có thể so sánh nội dung primitive arrays nên trả true.
3. `Objects.deepEquals(nestedA, nestedB)` đi qua các mảng con phù hợp để so sánh sâu.
4. `List.equals` so sánh nội dung theo vị trí; vì vậy hai `List.of("a","b")` có giá trị như nhau.
5. Nhưng `List<int[]>` (ở đây suy luận thông qua `List.of(new int[]{...})`) chứa array element; phép `List.equals` sẽ dùng `equals` của từng phần tử, tức **identity của hai array**. Vì vậy `list-of-arrays=false`. `Objects.equals` không tự chuyển thành `Arrays.deepEquals` chỉ vì danh sách chứa mảng.

**Lưu ý null:** `Arrays.equals` và `Arrays.deepEquals` có chính sách null rõ ràng cho mảng; khi cả hai mảng bằng null thì kết quả true. Nhưng chúng là API cho **array**, không thay thế `Objects.equals` ở mọi object.

### 7.2. Collections có hợp đồng equals riêng

Các collection chuẩn có equality theo contract của loại collection:

- `List`: các phần tử tương ứng bằng nhau theo cùng thứ tự.
- `Set`: cùng các phần tử, không phụ thuộc thứ tự lặp.
- `Map`: cùng các cặp key/value theo hợp đồng `Map.equals`.
- Các collection tùy chỉnh có thể có quy tắc riêng hoặc kế thừa identity-based equality. Kiểm tra JavaDoc của loại cụ thể.

Nếu phần tử của collection là các object mutable, hoặc có `equals` được định nghĩa sai, `Objects.equals(collectionA, collectionB)` **không sửa** những vấn đề đó.

## 8. Null là một giá trị thiếu: khi nào không được coi hai null là giống nhau?

`Objects.equals(null,null)` luôn true, nhưng nghiệp vụ có thể không muốn kết luận “tìm thấy đối tượng có cùng ID” khi cả hai ID đều bị thiếu.

Ví dụ có một hồ sơ `User` với mã `id` tùy chọn. Nếu caller tìm bằng mã trống (`requestedId == null`) và dữ liệu cũng có ID null, phép:

```java
Objects.equals(user.id(), requestedId)
```

sẽ trả true. Tùy nghiệp vụ, đây có thể là **false positive** nguy hiểm. Phải yêu cầu ID khác null ở cả hai phía nếu ý định là “khớp định danh đã có”.

Tạo tệp `BusinessNullDemo.java`:

```java
import java.util.Objects;

public class BusinessNullDemo {
    record User(String id, String email) {}

    static boolean matchesId(User user, String requestedId) {
        return user != null
                && requestedId != null
                && user.id() != null
                && Objects.equals(user.id(), requestedId);
    }

    public static void main(String[] args) {
        User missing = new User(null, "unknown@example.test");
        User known = new User("u-7", "real@example.test");

        System.out.println(
                "raw-two-missing="
                + Objects.equals(missing.id(), null));
        System.out.println(
                "matches-two-missing="
                + matchesId(missing, null));
        System.out.println(
                "matches-known="
                + matchesId(known, "u-7"));
        System.out.println(
                "matches-other="
                + matchesId(known, "u-8"));
        System.out.println(
                "matches-null-user="
                + matchesId(null, "u-7"));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BusinessNullDemo.java
java BusinessNullDemo
```

```text
raw-two-missing=true
matches-two-missing=false
matches-known=true
matches-other=false
matches-null-user=false
```

**Vì sao cần điều kiện bổ sung?** `Objects.equals` trả lời câu hỏi **hai reference/value theo `equals` có bằng nhau không**. `matchesId` trả lời câu hỏi **cả hai có định danh hợp lệ và giá trị định danh có trùng nhau không**. Đây là hai đặc tả khác nhau.

**Ví dụ thực tế:** không nên dùng `Objects.equals(authenticatedUserId, requestedUserId)` như một cơ chế kiểm tra quyền truy cập độc lập. Authorization còn cần xác thực phiên, quyền truy cập tài nguyên và chính sách tenant; equality của hai ID là điều kiện cần hoặc phụ tùy hệ thống, **không phải quyết định ủy quyền hoàn chỉnh**.

## 9. Khi nào Objects.equals không đủ?

### 9.1. So sánh không phân biệt chữ hoa/chữ thường

`String.equals` phân biệt chữ hoa/chữ thường. Do đó `Objects.equals("Java", "java")` false. Nếu ứng dụng cần case-insensitive matching, phải xác định **locale, Unicode normalization và quy tắc dữ liệu** rõ ràng; ví dụ đơn giản:

```java
boolean sameIgnoringCase = first != null
        ? first.equalsIgnoreCase(second)
        : second == null;
```

Đây là **đoạn minh họa trong method**. `String.equalsIgnoreCase` có đặc tả riêng và không phải giải pháp hoàn chỉnh cho mọi bài toán so khớp văn bản quốc tế hóa; không thay bằng `toLowerCase()` không chỉ định locale trong code xử lý định danh nhạy cảm.

### 9.2. So sánh số giữa các kiểu khác nhau

`Objects.equals(1, 1L)` false, `Objects.equals(new BigDecimal("1.0"), new BigDecimal("1.00"))` false. Nếu yêu cầu “bằng nhau về giá trị số”, hãy chọn **phép chuyển đổi nhất quán, chính xác** và comparator phù hợp, ví dụ `BigDecimal.compareTo` sau khi xác minh kiểu/đơn vị.

Không mặc định chuyển mọi `Number` sang `double` để so sánh, vì có thể mất chính xác đối với số nguyên lớn, decimal hoặc số tiền.

### 9.3. So sánh mảng/byte payload theo nội dung

Dùng `Arrays.equals` hoặc `Arrays.deepEquals` tùy cấu trúc. Không nghĩ `Objects.equals` tự truy cập tất cả bytes của một mảng. Nếu cần so sánh dữ liệu nhạy cảm về thời gian thực thi (ví dụ một số token bí mật), equality thông thường còn có thể không phù hợp yêu cầu side-channel; phải dùng API/chính sách mật mã được thiết kế đúng cho trường hợp đó.

### 9.4. So sánh dữ liệu có phiên bản/định danh nghiệp vụ

Hai entity có cùng dữ liệu field chưa chắc là “cùng entity”. Ngược lại, hai entity có ID giống nhau nhưng dữ liệu cập nhật khác nhau có thể vẫn được coi là một định danh. Cần xác định **ngữ nghĩa equals của domain**, không dùng `Objects.equals` như một công cụ tự động suy ra điều đó.

### 9.5. So sánh an toàn khi object bị thay đổi đồng thời

`Objects.equals` không tự đồng bộ trạng thái của hai object. Nếu các field được so sánh đang bị thread khác sửa, có thể thấy snapshot không nhất quán. Cần thiết kế immutable objects, synchronization hoặc snapshot theo nhu cầu; một phép null-safe equality **không giải quyết concurrency**.

## 10. Objects.equals trong các điều kiện thường gặp

### 10.1. Tìm kiếm trong Stream

Một ví dụ ngắn:

```java
boolean found = users.stream()
        .anyMatch(user ->
            Objects.equals(user.getExternalId(), requestedId));
```

Đây là **đoạn minh họa**, `users`, `getExternalId()` và `requestedId` do ứng dụng cung cấp. `Objects.equals` ở đây tránh null dereference khi ID nullable, **nhưng `user` tự nó phải khác null** trước khi gọi `getExternalId()`. Nếu danh sách có thể chứa null element, thêm `user != null` vào predicate.

Nếu nghiệp vụ không chấp nhận thiếu ID, thêm ràng buộc `requestedId != null` và `user.getExternalId() != null` (hoặc validate ở đầu luồng) để tránh coi hai ID thiếu là khớp.

### 10.2. Kiểm tra field cũ và field mới

```java
if (!Objects.equals(oldStatus, newStatus)) {
    // Chỉ xử lý khi hai status không bằng nhau theo equals().
}
```

Đây là **đoạn minh họa**. Với hai giá trị null, điều kiện false: theo ngữ nghĩa so sánh này, không có thay đổi. Nếu chuyển từ null sang giá trị thật hoặc ngược lại, kết quả true.

Khi `oldStatus`/`newStatus` là object mutable có `equals` phụ thuộc trạng thái, tránh lấy hai biến cùng trỏ tới một đối tượng đã bị sửa rồi mong `Objects.equals` phát hiện lịch sử thay đổi. Cần **snapshot giá trị trước khi sửa** nếu muốn audit thay đổi.

### 10.3. So sánh enum nullable

Với hai biến enum, `oldState == newState` đã là phép so sánh reference null-safe (mỗi hằng enum là một instance định danh). `Objects.equals(oldState,newState)` cũng hoạt động, nhưng có thể không cần thiết. Chọn cách rõ ràng và nhất quán với coding convention.

### 10.4. Khi biết một phía chắc chắn không null

`"READY".equals(status)` an toàn ngay cả khi `status` null và đơn giản. `Objects.equals("READY", status)` cũng đúng. Ưu tiên cách giúp người đọc hiểu ngay hợp đồng; không cần thay mọi lời gọi equals trực tiếp thành Objects.equals chỉ để “hiện đại hóa”.

## 11. Những lỗi phổ biến và cách sửa

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| `nullable.equals(value)` | Có thể ném NPE | Dùng `Objects.equals(nullable, value)` nếu hai null phải bằng nhau |
| `left == right` để kiểm tra nội dung String | Identity khác value equality | Dùng `Objects.equals(left,right)` hoặc `left.equals(right)` khi left non-null |
| `Objects.equals(a,b)` và cho rằng nó luôn “so sánh sâu” | Ủy quyền cho `a.equals(b)` | Với arrays dùng `Arrays.equals`/`deepEquals` phù hợp |
| `Objects.equals(1,1L)` và mong true | Integer và Long khác loại | Chuẩn hóa kiểu số có kiểm soát trước khi so sánh |
| `Objects.equals(null,null)` dùng làm bằng chứng hai ID hợp lệ | Hai giá trị thiếu vẫn được coi bằng nhau | Validate non-null theo yêu cầu domain |
| Override `equals` nhưng quên `hashCode` | Phá hợp đồng hash collections | Override cả hai theo cùng tập field |
| Dùng field mutable làm hash key | Hash thay đổi sau khi lưu | Immutable key hoặc chiến lược identity phù hợp |
| So sánh `byte[]` bằng `Objects.equals` | Array equals theo identity | `Arrays.equals(byte[],byte[])` |
| Tự động ép `String` thành `StringBuilder` qua `Objects.equals` | Không có chuyển kiểu tự động | Xác định cùng kiểu biểu diễn trước khi so sánh |
| Tin rằng Objects.equals sửa được equals bất đối xứng | Nó chỉ gọi `a.equals(b)` | Sửa implementation `equals` theo contract |
| Dùng Objects.equals làm authorization hoàn chỉnh | Equality không tự kiểm tra quyền | Tách authentication, authorization và điều kiện dữ liệu |
| So sánh old/new cùng tham chiếu mutable | Không lưu trạng thái quá khứ | Lấy immutable snapshot trước khi cập nhật |

## 12. Quy trình lựa chọn API so sánh

Khi cần so sánh hai giá trị có thể null, đặt câu hỏi theo thứ tự:

1. **Bạn so sánh reference hay giá trị?** Nếu cần identity, `==`. Nếu cần value equality, dùng `equals`/`Objects.equals` theo contract loại dữ liệu.
2. **Có thể null không?** Nếu có, `Objects.equals` là lựa chọn mặc định tốt cho **object references thông thường**, miễn quy tắc hai null bằng nhau phù hợp.
3. **Hai null có được coi bằng nhau trong nghiệp vụ?** Nếu không, thêm guard `a != null && b != null` hoặc validation đầu vào.
4. **Đối tượng có equals override đúng không?** Kiểm tra contract đối xứng/bắc cầu, field tham gia equality và `hashCode`.
5. **Có phải mảng không?** Dùng `Arrays.equals`/`Arrays.deepEquals` hoặc `Objects.deepEquals` theo độ sâu.
6. **Có khác kiểu số/cùng giá trị nhưng khác biểu diễn không?** Chọn comparator/normalization đúng lĩnh vực, không ép kiểu mất chính xác.
7. **Có dùng làm Set/Map key không?** Kiểm tra hashCode đồng bộ, chọn immutable key.
8. **Có yêu cầu case-insensitive, locale, schema hoặc security không?** Viết quy tắc riêng; `Objects.equals` không tự suy ra những yêu cầu này.
9. **Có concurrency hoặc alias mutable không?** Đảm bảo snapshot/ownership để so sánh một trạng thái nhất quán.
10. **Thêm unit tests.** Test null-null, null-value, value-null, value-value, cùng reference, hai object khác reference nhưng bằng giá trị, dữ liệu có cấu trúc và trường hợp sai kiểu.

## 13. Bài tập thực hành

**Bài 1 — Bảng null.** Chạy `NullSafeEqualsDemo`, đoán trước kết quả của `Objects.equals(null,null)`, `Objects.equals(null,"x")`, `Objects.equals("x",null)` và hai `new String("x")`. Giải thích vì sao `==` không tương đương với `Objects.equals`.

**Bài 2 — Custom value object.** Chạy `UserKeyEqualityDemo`. Bỏ override `hashCode` và xem vì sao `HashSet` không còn có hợp đồng nhất quán. Tạo test cho reflexive, symmetric, transitive, null và hash consistency.

**Bài 3 — Field nullable.** Đổi `externalId` của `UserKey` thành bắt buộc và dùng `Objects.requireNonNull` ở constructor. So sánh với thiết kế chấp nhận null. Phương án nào đúng phụ thuộc hợp đồng miền nghiệp vụ?

**Bài 4 — Array equality.** Chạy `ArraysAndCollectionsDemo`. Tạo hai `byte[]` bằng nội dung và so sánh với `Objects.equals`, `Arrays.equals` và `Objects.deepEquals`. Giải thích vì sao danh sách chứa hai array khác instance không tự có deep equality.

**Bài 5 — Records.** Chạy `RecordAndMoneyDemo`, thay `Bytes` bằng record chứa `List<Byte>` và quan sát equality. Nêu sự khác biệt về alias, performance và mutability so với `byte[]`.

**Bài 6 — BigDecimal.** Chạy `RecordAndMoneyDemo` và giải thích vì sao `Objects.equals` trả false cho `1.0` và `1.00`, trong khi `compareTo==0` là true. Viết chính sách chuẩn hóa số tiền trước khi lưu hoặc so sánh.

**Bài 7 — Business rules.** Chạy `BusinessNullDemo`. Hãy sửa `matchesId` để reject chuỗi rỗng/blank nếu yêu cầu ID hợp lệ; test đủ user null, requested ID null, hai ID null, đúng ID và sai ID.

**Bài 8 — Review code.** Một PR thay mọi `a.equals(b)` bằng `Objects.equals(a,b)`. Hãy kiểm tra nơi nào thật sự có nullable receiver, nơi nào cần array content equality, nơi nào yêu cầu ID non-null và nơi nào dùng enum/constant nên có cách đơn giản hơn.

## 14. Kết luận

- **`Objects.equals(a,b)` là null-safe equality cho object references**, với hai null bằng nhau và một null khác non-null là không bằng nhau khi `equals` tuân thủ contract.
- Khi cả hai object khác null và khác reference, nó dựa trên **`a.equals(b)`**; không sửa được implementation `equals` sai.
- **`==` kiểm tra identity** của reference, còn `Objects.equals` ưu tiên value equality nếu class override `equals` đúng cách.
- **`equals` và `hashCode` phải nhất quán** nếu object dùng trong hash-based collections; ưu tiên immutable value objects hoặc record phù hợp.
- **Arrays không được so sánh nội dung bằng `Objects.equals`**. Dùng `Arrays.equals` hoặc deep equality thích hợp cho cấu trúc nhiều tầng.
- **Hai giá trị null bằng nhau về mặt API nhưng không nhất thiết hợp lệ về nghiệp vụ**. Điều kiện non-null, permission và validation phải được thể hiện riêng.
- **`BigDecimal` và cross-type numbers có semantics riêng**; không tự động chuẩn hóa giá trị số trong `Objects.equals`.
- Java 17+ vẫn dùng trực tiếp `Objects.equals` (API Java 7), kết hợp record (Java 16+) và pattern matching for `instanceof` để viết value objects hiện đại.

## Tài liệu chính thức

- [Objects — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html): `equals`, `deepEquals`, `hash` và `hashCode`.
- [Object.equals — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): hợp đồng equality.
- [Arrays — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `equals` và `deepEquals` cho arrays.
- [BigDecimal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `equals` và `compareTo`.
- [JLS `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): equality tự sinh cho record components.
