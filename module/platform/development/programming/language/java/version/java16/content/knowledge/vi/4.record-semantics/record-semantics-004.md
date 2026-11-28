# `hashCode` được suy ra từ component và giới hạn phụ thuộc thuật toán

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được hoàn thiện trong Java 16 và tự cung cấp `equals(Object)`, `hashCode()` cùng `toString()` nếu lập trình viên không khai báo tường minh các phương thức đó. Với `hashCode()`, Java lấy thông tin từ các record component để tạo mã băm cho toàn bộ record. Quy tắc này giúp record hoạt động tự nhiên với `HashMap`, `HashSet` và các cấu trúc dữ liệu dựa trên hash.

Điều quan trọng là **kết quả phải tuân thủ hợp đồng `equals`/`hashCode`, còn thuật toán kết hợp các component không được đặc tả cố định**. Vì thế, mã băm phù hợp để hỗ trợ tra cứu trong collection, nhưng không phải định danh duy nhất hay giá trị có thể lưu trữ làm khóa bền vững giữa các lần chạy.

## 1. `hashCode` mặc định của record đến từ đâu?

Xét record:

```java
record EmployeeKey(String department, int number) {}
```

Nếu không tự khai báo `hashCode()`, compiler cung cấp phương thức này dựa trên các component `department` và `number`. Có thể hình dung ý tưởng ở mức khái niệm:

```java
// Mã minh họa khái niệm, không phải thuật toán compiler bắt buộc sinh.
int conceptualHash(EmployeeKey key) {
    int departmentHash =
        java.util.Objects.hashCode(key.department());
    int numberHash = Integer.hashCode(key.number());

    // Hàm kết hợp hai giá trị không được đặc tả cố định.
    return combine(departmentHash, numberHash);
}
```

`combine` ở trên chỉ là tên minh họa cho một phép kết hợp. Không có lời hứa rằng record dùng phép cộng, nhân với 31, `Objects.hash(...)`, hay một công thức cụ thể nào. Cũng không nên dựa vào thứ tự xử lý nội bộ hoặc giá trị số cuối cùng mà một compiler/JDK cụ thể tạo ra.

Với component tham chiếu:

- Giá trị `null` được xử lý an toàn và đóng góp mã băm theo ngữ nghĩa của giá trị tham chiếu rỗng (`Objects.hashCode(null)` trả về `0`).
- Nếu khác `null`, mã băm của component dựa trên `hashCode()` của chính đối tượng đó.
- Nếu component là một record khác, `hashCode()` của record lồng nhau tiếp tục được tính từ các component của nó.
- Nếu component là collection, quy tắc `hashCode()` của `List`, `Set` hoặc `Map` được sử dụng thông qua đối tượng thành phần.

Với component primitive, giá trị được băm theo quy tắc tương ứng với kiểu primitive và wrapper của nó. Không có boxing bắt buộc trong mã nguồn của bạn; đây là cách hiểu về ngữ nghĩa của kết quả:

| Component | Quy tắc hash tương ứng | Ghi chú |
| --- | --- | --- |
| `boolean` | `Boolean.hashCode(value)` | Hai trạng thái `true` và `false` có mã băm khác nhau. |
| `byte`, `short`, `char`, `int` | Wrapper tương ứng (`Byte`, `Short`, `Character`, `Integer`) | Giá trị được chuyển thành mã băm kiểu `int`. |
| `long` | `Long.hashCode(value)` | Kết hợp hai nửa 32 bit của giá trị `long`. |
| `float` | `Float.hashCode(value)` | Dựa trên biểu diễn bit chuẩn hóa của `float`. |
| `double` | `Double.hashCode(value)` | Dựa trên biểu diễn bit chuẩn hóa của `double`. |

Với `float` và `double`, các NaN được chuẩn hóa khi tính hash nên các dạng NaN có cùng mã băm; `+0.0` và `-0.0` vẫn có mã băm khác nhau. Điều này nhất quán với quy tắc `equals` của wrapper: NaN bằng NaN, còn hai dạng zero có dấu khác nhau.

Ví dụ, hai record cùng lớp và có cùng component sẽ có cùng mã băm:

```java
record Point(int x, int y) {}

Point first = new Point(10, 20);
Point second = new Point(10, 20);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Không cần hai biến tham chiếu trỏ đến cùng một đối tượng. Điều kiện là chúng bằng nhau theo `equals`; hợp đồng yêu cầu mã băm của chúng cũng bằng nhau.

## 2. Hợp đồng `Object.hashCode()` cần tuân thủ

Hợp đồng của `hashCode()` áp dụng cho mọi lớp Java, bao gồm record:

1. Trong cùng một lần chạy ứng dụng, nếu thông tin được dùng trong phép so sánh `equals` không thay đổi, gọi `hashCode()` nhiều lần trên cùng đối tượng phải trả về cùng một số nguyên.
2. Nếu `a.equals(b)` là `true`, thì `a.hashCode()` và `b.hashCode()` **bắt buộc bằng nhau**.
3. Nếu `a.equals(b)` là `false`, hai mã băm **vẫn có thể bằng nhau**. Đây là hiện tượng va chạm mã băm (*hash collision*).

Ví dụ:

```java
record ProductCode(String value) {}

ProductCode a = new ProductCode("P-100");
ProductCode b = new ProductCode("P-100");
ProductCode c = new ProductCode("P-200");

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // bắt buộc true

System.out.println(a.equals(c)); // false
// a.hashCode() == c.hashCode() có thể true hoặc false.
```

Không thể suy luận hai đối tượng bằng nhau chỉ vì mã băm giống nhau. Mã băm có phạm vi `int` 32 bit, trong khi số lượng giá trị đối tượng có thể lớn hơn rất nhiều; va chạm là điều bình thường.

### Minh họa va chạm một cách có chủ ý

Ta có thể tạo một component có `hashCode()` luôn trả về cùng một số nhưng `equals()` vẫn phân biệt giá trị:

```java
final class HashPart {
    private final String value;

    HashPart(String value) {
        this.value = java.util.Objects.requireNonNull(value, "value");
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof HashPart that
            && value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return 1; // Cố ý tạo va chạm để minh họa.
    }
}

record WrappedKey(HashPart part) {}

WrappedKey one = new WrappedKey(new HashPart("A"));
WrappedKey two = new WrappedKey(new HashPart("B"));

System.out.println(one.hashCode() == two.hashCode()); // true
System.out.println(one.equals(two));                  // false
```

Record sử dụng `equals()` và `hashCode()` của component. Vì `HashPart` tuân thủ hợp đồng (hai giá trị bằng nhau thì cùng hash; chiều ngược lại không bắt buộc), hai `WrappedKey` có cùng hash nhưng không bằng nhau. Đây là tình huống hợp lệ.

## 3. Thuật toán tạo hash của record không phải API ổn định

Đặc tả Java yêu cầu mã băm của record được suy ra từ các component và nhất quán với `equals`, nhưng **không quy định công thức kết hợp chính xác**. Thuật toán có thể khác giữa các implementation; mã băm cũng không được bảo đảm ổn định giữa những lần chạy khác nhau của cùng ứng dụng.

Điều này có một số hệ quả thực tế:

- Không viết logic nghiệp vụ phụ thuộc vào một số hash cụ thể, chẳng hạn cho rằng `new Point(1, 2).hashCode()` luôn bằng một hằng số nào đó.
- Không kiểm thử bằng cách đóng đinh kết quả hash cụ thể của record nếu mục tiêu chỉ là kiểm tra hợp đồng. Hãy kiểm tra `equals` kéo theo cùng `hashCode`.
- Không giả định `record.hashCode()` tương đương `Objects.hash(component1, component2)`. `Objects.hash` có thuật toán riêng; đặc tả không bắt buộc implementation của record phải dùng nó.
- Không dùng `hashCode()` làm ID, mã giao dịch, khóa lưu trữ, giá trị ký số hay dữ liệu trao đổi giữa các tiến trình.

Ví dụ không nên viết:

```java
record Coordinate(int x, int y) {}

Coordinate coordinate = new Coordinate(4, 9);

// Không làm như sau: giá trị cụ thể không phải hợp đồng của record.
// if (coordinate.hashCode() == 133) {
//     processSpecialCoordinate();
// }
```

Nếu cần định danh bền vững, hãy dùng dữ liệu component làm khóa nghiệp vụ, một ID được tạo rõ ràng (`UUID`, khóa cơ sở dữ liệu), hoặc một định dạng tuần tự hóa có hợp đồng ổn định. Đừng dùng hash code nội bộ thay cho định danh.

## 4. Vai trò của `hashCode` trong `HashMap` và `HashSet`

Các collection dựa trên hash dùng mã băm để tổ chức và tìm nhóm phần tử ứng viên. Sau đó, chúng cần `equals()` để xác định khóa/phần tử có thực sự bằng nhau hay không.

```java
import java.util.HashMap;
import java.util.Map;

record UserKey(String tenant, String username) {}

Map<UserKey, String> users = new HashMap<>();
users.put(new UserKey("acme", "linh"), "Linh");

String name = users.get(new UserKey("acme", "linh"));
System.out.println(name); // Linh
```

Đối tượng khóa truyền vào `get` là instance mới, nhưng có cùng lớp record và cùng giá trị component với khóa lúc `put`. Vì `equals` là `true` và `hashCode` nhất quán, collection có thể tìm đúng ánh xạ.

Với `HashSet`, nguyên tắc tương tự:

```java
import java.util.HashSet;
import java.util.Set;

record Permission(String resource, String action) {}

Set<Permission> permissions = new HashSet<>();
permissions.add(new Permission("invoice", "read"));
permissions.add(new Permission("invoice", "read"));
permissions.add(new Permission("invoice", "write"));

System.out.println(permissions.size()); // 2
```

Hai phần tử đầu bằng nhau nên tập hợp chỉ giữ một phần tử tương đương. Phần tử thứ ba có component `action` khác nên không bằng phần tử đầu, dù mã băm của chúng có thể trùng.

Mã băm tốt giúp phân bố phần tử hợp lý và giảm số lần so sánh va chạm, nhưng không thể thay thế `equals`. Với các collection hash, cả hai phương thức phải có hợp đồng đúng.

## 5. Component mutable có thể làm thay đổi hash sau khi tạo record

Các trường component của record là `final`, nhưng điều đó chỉ ngăn thay thế tham chiếu sau khi khởi tạo. Nó không tự làm đối tượng được tham chiếu trở nên bất biến.

Ví dụ, một record chứa `List` có thể nhận một danh sách mutable từ bên ngoài:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record SearchKey(List<String> filters) {}

List<String> filters = new ArrayList<>(List.of("active"));
SearchKey key = new SearchKey(filters);

Map<SearchKey, String> cache = new HashMap<>();
cache.put(key, "cached result");

filters.add("premium");
// hashCode của key thay đổi vì List.hashCode phụ thuộc vào phần tử.
// get(key) hoặc remove(key) có thể không tìm thấy entry đã chèn trước đó.
```

Sau khi chèn, collection đã tổ chức khóa dựa trên trạng thái hash lúc đó. Khi component thay đổi, mã băm mới có thể dẫn đến vị trí tra cứu khác. Đây là lý do không nên thay đổi dữ liệu tham gia `equals`/`hashCode` trong lúc đối tượng đang được dùng làm khóa hoặc phần tử của hash collection.

### Sao chép dữ liệu đầu vào trong constructor

Với danh sách chứa kiểu bất biến như `String`, có thể sao chép cấu trúc danh sách ngay khi tạo record:

```java
import java.util.List;

record SearchKey(List<String> filters) {
    SearchKey {
        filters = List.copyOf(filters);
    }
}
```

`List.copyOf` tạo danh sách không thể sửa qua API `List` và ngăn thay đổi cấu trúc thông qua tham chiếu danh sách đầu vào. Phương thức này không cho phép phần tử `null` và chỉ sao chép nông: nếu phần tử là đối tượng mutable, trạng thái của phần tử vẫn có thể thay đổi. Khi đó cần dùng phần tử bất biến hoặc sao chép/chuẩn hóa dữ liệu ở cấp sâu hơn.

### Mảng là trường hợp đặc biệt

Mảng không ghi đè `Object.equals()` và `Object.hashCode()`. Vì vậy record có component mảng dùng ngữ nghĩa danh tính của mảng, không tự tính hash từ từng phần tử:

```java
record ByteKey(byte[] bytes) {}

ByteKey a = new ByteKey(new byte[] {1, 2, 3});
ByteKey b = new ByteKey(new byte[] {1, 2, 3});

System.out.println(a.equals(b)); // false: hai mảng khác tham chiếu
```

Nếu yêu cầu nghiệp vụ là so sánh theo nội dung mảng, cần tự triển khai **cả** `equals` và `hashCode` bằng các phương thức phù hợp như `Arrays.equals` và `Arrays.hashCode`, đồng thời cân nhắc sao chép phòng vệ trong constructor và accessor. Chỉ ghi đè một trong hai phương thức có thể phá vỡ hợp đồng.

## 6. Component có `equals` tùy chỉnh thì `hashCode` phải tương ứng

Record dựa vào hợp đồng của component. Nếu component là một class tự viết, class đó phải bảo đảm:

```text
Nếu componentA.equals(componentB) == true
thì componentA.hashCode() == componentB.hashCode().
```

Nếu component triển khai `equals` theo nội dung nhưng `hashCode` theo danh tính, record chứa component đó có thể có hai instance bằng nhau nhưng hash khác nhau. Khi dùng record làm khóa, `HashMap`/`HashSet` có thể không xử lý đúng theo kỳ vọng.

Khi viết một value class thông thường, hãy ghi đè `equals` và `hashCode` cùng nhau. Với record, implementation mặc định đã làm việc này dựa trên các component; chỉ tùy chỉnh khi có một ngữ nghĩa giá trị thực sự cần thiết.

## 7. Khi nào nên ghi đè `hashCode` trong record?

Thông thường không cần. Nếu `equals` mặc định phù hợp với ý nghĩa dữ liệu, `hashCode` mặc định cũng là lựa chọn nên giữ.

Java cho phép khai báo tường minh `hashCode()` trong record. Nếu làm vậy, phải bảo đảm mọi cặp record bằng nhau theo `equals` đều có cùng hash. Nếu đồng thời tùy chỉnh `equals`, cần thiết kế hai phương thức như một cặp.

Ví dụ về một record có ngữ nghĩa bằng nhau tùy chỉnh theo nội dung mảng:

```java
import java.util.Arrays;
import java.util.Objects;

record ByteValue(byte[] bytes) {
    ByteValue {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof ByteValue that
                && Arrays.equals(this.bytes, that.bytes));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Ở đây, `equals` và `hashCode` cùng dùng ngữ nghĩa nội dung mảng; constructor và accessor sao chép mảng để tránh thay đổi từ bên ngoài. Đây là một trường hợp có chủ đích cần tùy chỉnh. Nếu chỉ cần một value object đơn giản, ưu tiên component có `equals`/`hashCode` theo giá trị sẵn có.

## 8. Kiểm thử hợp đồng thay vì kiểm thử công thức

Khi kiểm thử record, nên xác minh các thuộc tính được đặc tả:

```java
record Money(String currency, long minorUnits) {}

Money first = new Money("VND", 125_000);
Money second = new Money("VND", 125_000);
Money different = new Money("USD", 125_000);

assert first.equals(second);
assert first.hashCode() == second.hashCode();
assert !first.equals(different);
```

Khi chạy ví dụ có `assert`, bật assertions bằng tùy chọn `-ea` của JVM. Không cần yêu cầu `first.hashCode()` phải bằng một con số cố định. Một kiểm thử hợp đồng còn có thể xác minh tính ổn định khi component không đổi:

```java
int originalHash = first.hashCode();
assert first.hashCode() == originalHash;
```

Đối với component mutable, kiểm thử cần nhận thức rằng thay đổi dữ liệu có thể làm thay đổi hash. Cách tốt hơn thường là ngăn trạng thái mutable lọt vào value object được dùng làm khóa.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Hai record bằng nhau phải có cùng `hashCode`. | **Đúng** | Đây là hợp đồng bắt buộc của `Object`. |
| Hai record có cùng `hashCode` chắc chắn bằng nhau. | **Sai** | Va chạm mã băm là hợp lệ. |
| Thuật toán hash của record luôn là `Objects.hash(...)`. | **Sai** | Công thức kết hợp không được đặc tả cố định. |
| Hash code của record ổn định giữa các phiên bản JDK và các lần chạy. | **Sai** | Không có bảo đảm như vậy trong đặc tả. |
| Trường component `final` khiến hash không thể thay đổi. | **Sai** | Đối tượng mutable được tham chiếu vẫn có thể thay đổi trạng thái. |
| Mảng trong record tự động được hash theo nội dung. | **Sai** | Mảng dùng `equals`/`hashCode` kế thừa từ `Object`. |
| Có thể dùng `hashCode` làm ID duy nhất của record. | **Sai** | Hash có thể va chạm và không phải định danh bền vững. |

## 10. Checklist thiết kế record dùng trong hash collection

1. Xác định `equals` mặc định theo component có đúng với ý nghĩa nghiệp vụ không.
2. Dùng các component có `equals`/`hashCode` nhất quán.
3. Tránh component mutable; sao chép phòng vệ hoặc chuẩn hóa dữ liệu khi cần.
4. Với mảng, quyết định rõ cần so sánh theo danh tính hay theo nội dung; nếu theo nội dung, triển khai cả `equals` và `hashCode`.
5. Không phụ thuộc công thức hoặc số hash cụ thể do một JDK tạo ra.
6. Không dùng hash code làm ID, khóa lưu trữ lâu dài hoặc dữ liệu truyền giữa các hệ thống.
7. Khi kiểm thử, xác minh hợp đồng `equals` kéo theo cùng `hashCode`, thay vì kiểm tra một hằng số hash.

**Ghi nhớ:** `hashCode()` mặc định của record được suy ra từ các component và phải nhất quán với `equals()`. Java không cam kết công thức kết hợp cụ thể, không bảo đảm hash duy nhất hoặc ổn định giữa các lần chạy. Hãy dùng hash code cho mục đích tổ chức và tra cứu collection; dùng component hoặc ID nghiệp vụ riêng cho định danh bền vững.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.lang.Object.hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#hashCode()).
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
