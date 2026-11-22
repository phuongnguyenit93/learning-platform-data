# Cú pháp khai báo tham số kiểu của phương thức

## 1. Vì sao phương thức cần tham số kiểu?

Giả sử cần một phương thức nhận một giá trị rồi trả lại chính giá trị đó. Nếu viết `Object identity(Object value)`, nó nhận được nhiều loại đối tượng, nhưng kết quả chỉ có kiểu tĩnh là `Object`. Bên gọi không còn nhận trực tiếp được kiểu ban đầu mà không kiểm tra hoặc ép kiểu.

Phương thức generic cho phép mô tả **mối quan hệ kiểu giữa các vị trí trong hợp đồng của phương thức**. Ví dụ, kiểu dữ liệu đầu vào và kiểu kết quả được liên kết bằng cùng tham số kiểu `T`:

```java
public static <T> T identity(T value) {
    return value;
}
```

`<T>` là phần **khai báo tham số kiểu của phương thức**. `T` sau đó được dùng như một kiểu trong phạm vi phương thức. Bên gọi không truyền một “đối tượng T”; họ truyền đối tượng thông thường, còn trình biên dịch xác định đối số kiểu phù hợp cho lời gọi.

Ví dụ này dùng kiến thức generic còn áp dụng trong Java hiện hành. Các chương trình đầy đủ bên dưới chạy với Java 17 trở lên.

## 2. Vị trí của danh sách tham số kiểu

Dạng thường gặp của một phương thức có thân:

```text
[các từ khóa bổ nghĩa] <danh sách tham số kiểu> kiểu_trả_về tên_phương_thức(tham_số) {
    thân_phương_thức
}
```

Đây là sơ đồ cú pháp để đọc, không phải mã Java đem biên dịch. Dấu ngoặc vuông biểu thị phần có thể vắng mặt. Các thành phần thông thường khác của phương thức, chẳng hạn mệnh đề `throws` sau danh sách tham số, vẫn áp dụng khi cần.

Tách ví dụ `public static <T> T identity(T value)`:

| Thành phần | Vai trò |
| --- | --- |
| `public` | Mức truy cập |
| `static` | Phương thức thuộc lớp; không cần đối tượng để gọi |
| `<T>` | Khai báo tham số kiểu của chính phương thức |
| `T` trước `identity` | Kiểu trả về |
| `identity` | Tên phương thức |
| `T value` | Tham số giá trị tên `value`, có kiểu `T` |

Thứ tự cần nhớ: **phần bổ nghĩa → `<T>` → kiểu trả về → tên phương thức**. Không đặt phần khai báo `<T>` sau kiểu trả về hoặc sau tên phương thức.

```java
// Đúng: public static <T> T identity(T value) { return value; }
// Sai:  public static T <T> identity(T value) { return value; }
// Sai:  public static T identity<T>(T value) { return value; }
```

Trong các dòng trên, phần sai chỉ là chú thích minh họa lỗi cú pháp, không phải các phương thức bổ sung cần viết vào chương trình.

Tên `T` là quy ước, không phải từ khóa. Có thể dùng `E`, `K`, `V`, `R` hoặc tên khác có ý nghĩa. Java phân biệt chữ hoa và chữ thường; quy ước viết hoa giúp phân biệt tham số kiểu với biến giá trị.

## 3. Khai báo kiểu khác với sử dụng kiểu

So sánh các khai báo sau; chúng cần được đặt trong một lớp và có import `java.util.List`:

```java
static <T> T echo(T value) {
    return value;
}

static List<String> labels() {
    return List.of("small", "large");
}

static <T> List<T> one(T value) {
    return java.util.Collections.singletonList(value);
}
```

- `echo` là phương thức generic vì nó tự khai báo `<T>`.
- `labels` trả về một kiểu generic đã được tham số hóa là `List<String>`, nhưng bản thân phương thức **không generic**: nó không khai báo tham số kiểu riêng.
- `one` vừa là phương thức generic, vừa trả về kiểu generic `List<T>`. `<T>` trước `List<T>` là khai báo; `T` bên trong `List<T>` là một lần sử dụng tham số kiểu đó.

Cũng cần phân biệt hai loại tham số:

```text
<T>                tham số kiểu: dùng khi kiểm tra kiểu
(T value)          tham số giá trị: nhận dữ liệu khi gọi phương thức
```

Dùng tên `T` ở kiểu trả về hoặc tham số mà chưa khai báo nó trong phạm vi hợp lệ sẽ gây lỗi biên dịch. Trình biên dịch không tự coi mọi chữ cái viết hoa là tham số kiểu.

## 4. Phạm vi của tham số kiểu thuộc phương thức

Một tham số kiểu được khai báo trên phương thức thuộc phạm vi khai báo phương thức đó, dùng trong kiểu trả về, kiểu tham số và phần thân; nó không trở thành tham số kiểu của lớp chứa phương thức.

```java
class Helpers {
    static <T> T keep(T value) {
        T local = value;
        return local;
    }

    static <T> T keepAgain(T value) {
        return value;
    }
}
```

Hai chữ `T` trong hai phương thức là hai khai báo độc lập. Gọi `Helpers.keep("abc")` không cố định kiểu của `keepAgain` hoặc của mọi lần gọi `keep` trong tương lai.

Lớp `Helpers` không có `<T>` sau tên lớp nên không phải lớp generic. Một lớp thông thường vẫn có thể chứa phương thức generic. `static` cũng không phải điều kiện bắt buộc: một phương thức thể hiện có thể khai báo tham số kiểu riêng, ví dụ `public <R> R pass(R value)`.

Khi lớp bao quanh đã có tham số kiểu, nên dùng tên khác cho tham số kiểu độc lập của phương thức để tránh che khuất và gây hiểu nhầm. Để nhận biết phương thức có tự khai báo generic hay không, hãy tìm danh sách `<...>` đứng **trước kiểu trả về** của nó.

## 5. Một, nhiều hoặc có giới hạn tham số kiểu

### Một tham số có thể xuất hiện ở nhiều vị trí

```java
static <T> T firstOr(T value, T fallback) {
    return value != null ? value : fallback;
}
```

Cùng một `T` liên kết các vị trí trong chữ ký. Phần thân nhận các giá trị phù hợp với `T` và phải trả về giá trị phù hợp với `T`. Nó không được tự ý trả về một đối tượng bất kỳ chỉ vì `T` chưa cố định khi viết mã.

Cùng `T` không có nghĩa là các đối số bắt buộc có cùng lớp thực tế. Trình biên dịch có thể tìm một kiểu chung phù hợp với ngữ cảnh. Khi API cần một điều kiện mạnh hơn về kiểu thực tế hoặc nghiệp vụ, không nên suy ra điều kiện đó chỉ từ việc hai tham số cùng dùng `T`.

### Nhiều tham số kiểu được ngăn bằng dấu phẩy

```java
static <K, V> java.util.Map<K, V> singleEntry(K key, V value) {
    java.util.Map<K, V> result = new java.util.LinkedHashMap<>();
    result.put(key, value);
    return result;
}
```

`K` và `V` là hai tham số kiểu độc lập: khóa và giá trị không cần cùng kiểu. `<K, V>` là một danh sách khai báo duy nhất; không viết `<K><V>`.

Ở lời gọi tạo `Map<String, Integer>`, `K` có thể được xác định là `String` và `V` là `Integer`. Đừng viết `<String, Integer>` trong phần khai báo chỉ để đặt tên hai tham số kiểu: trong phần khai báo, đó sẽ là **tên biến kiểu mới**, dễ che khuất tên các lớp thật và làm người đọc hiểu sai ý định. Hãy dùng tên như `K` và `V`.

### Giới hạn trên dùng extends

```java
static <N extends Number> double asDouble(N value) {
    return value.doubleValue();
}
```

Giới hạn `N extends Number` cho phép phần thân dùng những phương thức được bảo đảm bởi `Number`. `asDouble(2)` hợp lệ nhờ boxing sang `Integer`; `asDouble("2")` không hợp lệ về kiểu.

Trong khai báo giới hạn, `extends` dùng cho cả lớp và giao diện, không thay bằng `implements`. Giới hạn nhiều điều kiện dùng dấu `&`, chẳng hạn `<T extends Number & Comparable<T>>`. Nếu có một giới hạn lớp trong danh sách nhiều giới hạn, lớp phải đứng trước các giao diện; không được đưa vào nhiều lớp khác nhau như nhiều lớp cha.

Không dùng `<T super Number>` để khai báo tham số kiểu. Cú pháp `? super Number` thuộc wildcard ở nơi sử dụng kiểu, có vai trò khác với danh sách khai báo tham số kiểu của phương thức.

Giới hạn kiểu cũng không tự bảo đảm dữ liệu khác `null`. `asDouble(null)` có thể phù hợp về kiểu nhưng gây `NullPointerException` khi gọi `doubleValue()`. Khi viết API thật, cần xác định hợp đồng `null`. Chuyển sang `double` cũng có thể làm mất độ chính xác của một số loại số; ví dụ này minh họa giới hạn kiểu, không phải phép chuyển đổi chính xác cho mọi miền tính toán.

## 6. Kiểu trả về không nhất thiết là tham số kiểu

Phương thức generic có thể trả về `void`, một kiểu nguyên thủy hoặc một kiểu cụ thể, miễn phần khai báo có tham số kiểu riêng:

```java
static <T> int count(java.util.List<T> items) {
    return items.size();
}

static <T> void printValue(T value) {
    System.out.println(value);
}
```

Trong `count`, `<T>` vẫn nằm trước `int`. Trong `printValue`, nó nằm trước `void`. Vì vậy, không thể nhận biết phương thức generic chỉ bằng việc thấy chữ `T` ở kiểu trả về.

Về thiết kế, nếu phương thức chỉ đọc kích thước danh sách và không cần liên kết kiểu với vị trí nào khác, `int count(List<?> items)` có thể diễn đạt ý định gọn hơn. Ví dụ trên dùng để nhận biết cú pháp; không nên thêm tham số kiểu không cần thiết cho mọi phương thức.

## 7. Chương trình chạy đầy đủ

Lưu thành **`GenericMethodSyntaxDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GenericMethodSyntaxDemo {
    public static <T> T identity(T value) {
        return value;
    }

    public static <T> List<T> one(T value) {
        return java.util.Collections.singletonList(value);
    }

    public static <K, V> Map<K, V> singleEntry(K key, V value) {
        Map<K, V> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    public static <N extends Number> double asDouble(N value) {
        return value.doubleValue();
    }

    public static <T> int count(List<T> items) {
        return items.size();
    }

    public static void main(String[] args) {
        String language = GenericMethodSyntaxDemo.<String>identity("Java");
        Integer level = identity(12);
        List<String> status = one("ready");
        Map<String, Integer> entry = singleEntry("level", 3);

        System.out.println(language);
        System.out.println(level);
        System.out.println(status);
        System.out.println(entry);
        System.out.println(asDouble(3.5));
        System.out.println(count(List.of("a", "b")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all GenericMethodSyntaxDemo.java
java GenericMethodSyntaxDemo
```

Stdout chính xác:

```text
Java
12
[ready]
{level=3}
3.5
2
```

Trong chương trình, mỗi phương thức tự khai báo các tham số kiểu mà nó cần. Chương trình không cần `class GenericMethodSyntaxDemo<T>` vì không lưu trạng thái đối tượng phụ thuộc một kiểu chung cho toàn bộ lớp.

`one` dùng `Collections.singletonList` để trả về danh sách một phần tử không cho thay đổi cấu trúc hay thay thế phần tử. Khả năng thay đổi của danh sách là hợp đồng của đối tượng danh sách, không phải điều do `<T>` quyết định.

## 8. Đối số kiểu tại lời gọi: suy luận và chỉ định tường minh

Ở phần khai báo:

```java
public static <T> T identity(T value) {
    return value;
}
```

`T` là **tham số kiểu**. Ở lời gọi `GenericMethodSyntaxDemo.<String>identity("Java")`, `String` là **đối số kiểu** cụ thể.

Chú ý vị trí tại lời gọi: đặt `<String>` **sau dấu chấm và trước tên phương thức**, không viết `identity<String>("Java")`.

Thông thường có thể để trình biên dịch suy luận từ đối số giá trị và ngữ cảnh mong đợi:

```java
String text = GenericMethodSyntaxDemo.identity("hello");
Integer number = GenericMethodSyntaxDemo.identity(8);
```

Dòng thứ hai boxing `8` thành `Integer`; đối số kiểu không phải `int`. Nếu chỉ định tường minh, dùng `<Integer>`, không dùng `<int>`.

Phần khai báo generic vẫn cần `<T>` dù mọi bên gọi đều dùng suy luận. Suy luận giảm thao tác ở **nơi gọi**, không tự sinh ra tham số kiểu còn thiếu trong **nơi khai báo**.

Một phương thức cũng có thể có tham số kiểu chỉ xuất hiện ở kiểu trả về. Ví dụ trong thư viện chuẩn:

```java
List<String> empty = java.util.Collections.emptyList();
```

`emptyList` có khai báo generic `<T> List<T> emptyList()`; không có tham số giá trị để truyền `T`, nên ngữ cảnh bên gọi giúp xác định kiểu phù hợp. Nó không có nghĩa phương thức có quyền trả về tùy ý một danh sách đang chứa các phần tử không phù hợp với `T`.

## 9. Lỗi thường gặp khi tự viết khai báo

### Dùng T nhưng quên khai báo

Trong một lớp không có tham số kiểu `T`, khai báo sau không hợp lệ:

```java
// static T echo(T value) { return value; }
```

Cách sửa là xác định đúng nhu cầu rồi khai báo `static <T> T echo(T value)`. Không thêm `<T>` tùy tiện vào lớp nếu chỉ một thao tác cần tổng quát hóa.

### Trả về đối tượng không phù hợp với T

```java
// static <T> T wrong(T input) { return "always text"; }
```

Không hợp lệ vì bên gọi có thể cần kết quả là `Integer`, trong khi phần thân cố trả về `String`. Java kiểm tra phần thân dựa trên ràng buộc đã khai báo, không chờ đến một lời gọi cụ thể để bỏ qua mâu thuẫn ấy.

Với `identity`, `return value` an toàn vì `value` đã có kiểu `T`. Ép kiểu không được kiểm tra chỉ che dấu một hợp đồng sai; nó không biến giá trị trả về thành kiểu mà bên gọi yêu cầu.

### Tưởng T có sẵn mọi phương thức

Nếu không có giới hạn rõ ràng, giới hạn trên của tham số kiểu là `Object`. Không thể gọi `value.length()` trên `T` bất kỳ. Nếu chỉ làm việc với chuỗi, dùng `String`; nếu thuật toán cần một khả năng chung, khai báo giới hạn phù hợp với khả năng đó.

### Nhầm tham số kiểu với một lớp có thể khởi tạo trực tiếp

`new T()` không hợp lệ. Khai báo `<T>` không bảo đảm kiểu cụ thể có constructor không tham số hoặc thậm chí là một lớp cụ thể có thể khởi tạo. Nhu cầu tạo đối tượng cần một thiết kế khác, chẳng hạn nhận một hàm tạo giá trị; không xử lý bằng cách sửa vị trí của `<T>`.

### Tạo overload chỉ khác tên tham số kiểu

`<T> T echo(T value)` và `<U> U echo(U value)` không phải hai cách nạp chồng khác nhau. Đổi tên tham số kiểu không tạo ra một hợp đồng phương thức mới có thể cùng tồn tại với hợp đồng cũ trong cùng lớp.

## 10. Tự thực hành

1. Viết `static <E> E pass(E element)` và gọi một lần với `String`, một lần với `Long`. Kiểm tra bên gọi nhận kết quả đúng kiểu mà không cần ép kiểu.
2. Đổi `pass` để khai báo `<R>` và cập nhật mọi chỗ dùng tham số kiểu trong phương thức. Hành vi phải giữ nguyên.
3. Viết phương thức `<A, B>` trả về `Map<A, B>` có một ánh xạ, rồi gọi bằng khóa `Integer` và giá trị `String`.
4. Thử đặt `<T>` sau kiểu trả về để quan sát lỗi cú pháp; sau đó khôi phục đúng vị trí.
5. Giải thích vì sao `List<String> labels()` không phải phương thức generic, còn `<T> int count(List<T> items)` là phương thức generic.

Khi đọc một phương thức, hãy tách rõ nơi **khai báo** tham số kiểu, nơi **sử dụng** tham số đó và nơi **chọn đối số kiểu** ở lời gọi. Ba vai trò ấy giúp đọc đúng cú pháp mà không nhầm generic của phương thức với kiểu trả về hoặc generic của lớp.

## Tài liệu đối chiếu

- [JLS §8.4.4 — Generic Methods](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.4): khai báo và ý nghĩa tham số kiểu của phương thức.
- [JLS §18.5 — Uses of Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html#jls-18.5): suy luận kiểu tại lời gọi phương thức.
- [Collections.emptyList — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#emptyList()): ví dụ phương thức generic của thư viện chuẩn.
