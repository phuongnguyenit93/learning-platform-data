# Đọc mã `var` ngoài IDE qua tài liệu và bản so sánh thay đổi

> **Phạm vi:** Hướng dẫn đọc, xác định kiểu và review những khai báo `var` khi chỉ có mã nguồn, Javadoc/tài liệu API và bản so sánh thay đổi (Git diff hoặc trang Changes của pull request). Các quy tắc đến từ tính năng **local-variable type inference** của Java 10 và vẫn áp dụng trên JDK hiện đại. Không cần dùng Java 10 đã cũ hay công cụ IDE cụ thể.

## 1. Vì sao cần kỹ năng đọc `var` ngoài IDE?

Trong IDE, người đọc có thể rê chuột lên `var` để thấy kiểu suy luận. Nhưng một pull request, email chứa diff, tài liệu Markdown, màn hình code review trên điện thoại hoặc một dòng log build có thể **không có thông tin hover**. Khi đó, chỉ nhìn:

```java
var result = repository.findActive();
```

thì **chưa đủ** để khẳng định `result` là `List<Customer>`, `Set<Customer>` hay `Optional<Customer>`. Phải tra chữ ký thực tế của `findActive()` (và các lớp, generic type liên quan) trong phiên bản mã đang review.

Mục tiêu là trả lời bốn câu hỏi bằng **bằng chứng có thể kiểm tra**:

1. `var` được compiler suy luận thành **kiểu tĩnh nào** ngay tại initializer?
2. Kiểu đó đến từ literal, constructor, generic method, chữ ký một phương thức nội bộ hay từ phép biến đổi trong Stream?
3. Bản diff có đổi initializer, chữ ký hàm, type argument, overload hoặc cách dùng biến, khiến suy luận thay đổi hay không?
4. Kiểu suy luận có rõ cho người review và có giữ đúng ràng buộc nghiệp vụ, hay nên viết kiểu tường minh?

Các bước trong bài dùng quy tắc Java Language Specification (JLS) và Java API đang được hỗ trợ. Với mã nguồn ứng dụng, thông tin từ **chữ ký thật trong commit đang xét** quan trọng hơn việc đoán theo tên phương thức.

## 2. Quy tắc nền: `var` là kiểu tĩnh, không phải kiểu động

`var` xuất hiện với biến cục bộ có initializer từ Java 10. Compiler **suy luận kiểu từ biểu thức khởi tạo** và dùng kiểu đó để kiểm tra toàn bộ các lần sử dụng tiếp theo.

```java
var title = "Java";                // String
var count = 5;                     // int
var amount = 5L;                   // long
var names = java.util.List.of("An", "Binh"); // List<String>
```

Sau dòng đầu, `title` là một biến kiểu `String`. Gán `title = 123;` là lỗi biên dịch; `var` không khiến biến được tự đổi kiểu lúc chạy.

**Điểm có ảnh hưởng lớn khi đọc mã:** initializer của `var` được xử lý như **standalone expression**, không nhận *target type* từ khai báo biến bên trái. Do đó:

```java
java.util.List<String> a = new java.util.ArrayList<>();
var b = new java.util.ArrayList<>();
```

- `a` có kiểu khai báo `List<String>`. Vế trái cung cấp target type giúp toán tử diamond `<>` suy luận `String`.
- `b` có kiểu suy luận `ArrayList<Object>` khi dùng constructor không đối số và không có ngữ cảnh kiểu khác để giới hạn tham số `E`.
- Hai dòng **không tương đương** chỉ vì chúng cùng tạo một danh sách rỗng. Một bản refactor thay khai báo tường minh bằng `var` có thể làm mất ràng buộc generic ngay cả khi code vẫn biên dịch.

Đọc từ vế phải sang vế trái: **tìm kiểu của initializer trước, sau đó mới xác định kiểu biến**. Đừng dựa vào tên biến hoặc những gì biến sẽ chứa trong tương lai.

## 3. Quy trình truy kiểu khi không có hover của IDE

### Bước 1 — Tìm đầy đủ khai báo và initializer

Xác định cả biểu thức sau dấu `=`, không chỉ phần đầu dòng. Với initializer trải nhiều dòng, cần theo đến hết dấu chấm phẩy:

```java
var activeNames = names.stream()
        .filter(name -> name.length() >= 3)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Không thể suy luận `activeNames` chỉ bằng việc thấy `stream()`. Cần đọc `filter` và **toàn bộ** lời gọi `collect`. Nếu initializer là lời gọi hàm nội bộ, tìm đến **đúng khai báo hàm** trong bản mã của commit đang review.

### Bước 2 — Xác định nguồn cung cấp kiểu

| Dạng initializer | Cách tìm kiểu tĩnh ngoài IDE | Ví dụ |
| --- | --- | --- |
| Literal hoặc phép toán | Đọc quy tắc Java của biểu thức | `var n = 10;` → `int`; `var n = 10L;` → `long`. |
| `new` có type argument rõ | Kiểu của biểu thức tạo đối tượng | `var list = new ArrayList<String>();` → `ArrayList<String>`. |
| `new` với diamond `<>` | Xem **đối số constructor** và target type thực có | `var list = new ArrayList<>();` → `ArrayList<Object>` trong trường hợp không có đối số. |
| Phương thức thường | Tra **return type** trong khai báo/Javadoc | `var ids = loadCodes();`; nếu `loadCodes(): List<String>`, kiểu là `List<String>`. |
| Phương thức generic | Đọc type parameter, tham số, type witness và kết quả suy luận | `var empty = Collections.emptyList();` → `List<Object>` khi không có ngữ cảnh khác. |
| Stream chain | Đi theo generic type qua từng lời gọi và collector cuối | `List<String>` → `filter` → `toUnmodifiableList` cho `List<String>`. |
| `Optional` | Tra kiểu của giá trị đi vào `Optional` | `Stream<String>.findFirst()` → `Optional<String>`. |
| Phép ép kiểu | Kiểu của toàn bộ biểu thức cast | `var text = (String) object;` → `String`. |

Nếu không thể tìm thấy chữ ký đúng phiên bản, kết luận đúng là **“chưa đủ thông tin để xác định kiểu”**. Không tự khẳng định kiểu dựa vào tên `load`, `find`, `getAll` hay loại dữ liệu thấy trong một ảnh chụp kết quả.

### Bước 3 — Đọc chữ ký trong Javadoc hoặc mã nguồn

Ví dụ Javadoc của `Collections.emptyList()` cho biết đây là phương thức generic với kiểu kết quả `List<T>`, nhưng không có đối số để xác định `T`:

```java
var unknown = java.util.Collections.emptyList();          // List<Object>
java.util.List<String> known = java.util.Collections.emptyList();
var explicit = java.util.Collections.<String>emptyList(); // List<String>
```

Dòng đầu thiếu target type từ `var` nên `T` được suy luận là `Object`. Dòng hai nhận target từ khai báo `List<String>`; dòng ba dùng **type witness** `<String>`.

Với hàm nội bộ:

```java
static java.util.List<String> loadCodes() {
    return java.util.List.of("A1", "B22");
}

// Trong một phương thức:
var codes = loadCodes(); // List<String>, vì chữ ký loadCodes() khai báo như vậy.
```

Hãy kiểm tra cả type parameter của **lớp chứa hàm** nếu lời gọi tới generic repository/service. Ví dụ một phương thức có chữ ký `T findById(ID id)` trong một lớp generic chỉ có thể suy luận đủ khi đã biết `T` và `ID` ở đối tượng nhận lời gọi. Không nên đoán rằng mọi `findById` đều trả `Optional<T>`; hợp đồng cụ thể tùy thư viện và dự án.

### Bước 4 — Lần theo từng phép biến đổi có ảnh hưởng kiểu

```java
var matches = loadCodes().stream()
        .filter(s -> s.startsWith("B"))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Nếu `loadCodes()` trả `List<String>`: `stream()` cho `Stream<String>`; `filter(...)` vẫn là `Stream<String>`; collector cuối trả `List<String>`. Dòng `var matches` vì vậy có kiểu `List<String>`.

Không cần biết compiler tạo đối tượng collection nội bộ nào mới xác định được **kiểu tĩnh**. Đồng thời, đừng suy diễn tính mutable chỉ từ tên concrete class: `Collectors.toUnmodifiableList()` tạo một danh sách không cho phép cập nhật cấu trúc.

### Bước 5 — Đọc những nơi dùng biến và overload

Sau khi tìm ra kiểu suy luận, kiểm tra cách biến được truyền đến các phương thức, nhất là nơi có overload. `Object value = "abc";` và `var value = "abc";` có thể chọn hai overload khác nhau bởi kiểu tĩnh lần lượt là `Object` và `String`.

Cũng chú ý API đòi `List<String>`: một biến `var data = new ArrayList<>();` có kiểu `ArrayList<Object>` không thể truyền trực tiếp vào vị trí yêu cầu `List<String>`. Nếu trước khi refactor mã biên dịch được, bản diff thay đổi type argument có thể là nguyên nhân build hỏng.

### Bước 6 — Kiểm tra loại thay đổi trong diff

So sánh **cả dòng khai báo `var`, initializer và chữ ký hàm được gọi**, kể cả những thay đổi ở tệp khác. Câu hỏi trọng tâm là: “Nếu bỏ chữ `var` và viết ra kiểu compiler suy luận ở commit cũ và commit mới, hai kiểu có còn đúng hợp đồng không?”

### Bước 7 — Kiểm chứng bằng compiler khi có thể

Nếu có quyền chạy mã, biên dịch hoặc chạy test bằng JDK được hỗ trợ. Compiler giúp phát hiện sai kiểu, lỗi overloading và generic mismatch. Tuy nhiên, **một khai báo `var` bị rộng thành `ArrayList<Object>` vẫn có thể biên dịch**; việc code build xanh không tự chứng minh rằng ý định generic ban đầu đã được bảo toàn.

## 4. Lab độc lập: suy luận kiểu bằng chữ ký và dữ liệu mã nguồn

Bài dùng JDK hiện đại được nhà cung cấp hỗ trợ (chẳng hạn một bản phân phối JDK 21 hoặc 25 LTS đang được cập nhật). Không cần JDK 10. Ví dụ chủ động dùng `Collectors.toUnmodifiableList/Map` được giới thiệu trong Java 10 và vẫn có mặt trên JDK hiện nay.

Kiểm tra phiên bản:

```bash
java -version
javac -version
```

Lưu chương trình đầy đủ thành **`ReadVarWithoutIde.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ReadVarWithoutIde {
    static List<String> loadCodes() {
        return List.of("A1", "B22", "C333");
    }

    static Map<String, Integer> lengthsOf(List<String> codes) {
        return codes.stream()
                .collect(Collectors.toUnmodifiableMap(
                        s -> s, String::length));
    }

    static String choose(Object x) { return "Object"; }
    static String choose(String x) { return "String"; }

    public static void main(String[] args) {
        // Kiểu đến từ chữ ký hàm nội bộ.
        var codes = loadCodes();                 // List<String>
        var lengths = lengthsOf(codes);          // Map<String, Integer>

        // Kiểu đến từ generic API và các bước Stream.
        var longCodes = codes.stream()
                .filter(s -> s.length() > 2)
                .collect(Collectors.toUnmodifiableList()); // List<String>
        var match = codes.stream()
                .filter(s -> s.startsWith("B"))
                .findFirst();                             // Optional<String>
        var total = lengths.values().stream()
                .mapToInt(Integer::intValue).sum();        // int

        // Kiểm tra trường hợp diamond làm generic rộng thành Object.
        var mixed = new ArrayList<>();           // ArrayList<Object>
        mixed.add("text");
        mixed.add(42);

        // Khai báo tường minh giữ type argument String.
        List<String> typed = new ArrayList<>();
        typed.add("safe");

        var genericEmpty = Collections.emptyList(); // List<Object>
        List<Object> compileTimeProof = genericEmpty;
        var typedEmpty = Collections.<String>emptyList(); // List<String>

        // Overload phụ thuộc kiểu tĩnh; không dựa vào kiểu runtime.
        var label = "ready"; // String
        Object asObject = label;

        System.out.println("codes: " + codes);
        System.out.println("longCodes: " + longCodes);
        System.out.println("length(B22): " + lengths.get("B22"));
        System.out.println("total length: " + total);
        System.out.println("first B: " + match.orElse("missing"));
        System.out.println("mixed: " + mixed);
        System.out.println("typed: " + typed);
        System.out.println("empty sizes: "
                + compileTimeProof.size() + "/" + typedEmpty.size());
        System.out.println("choose(label): " + choose(label));
        System.out.println("choose(asObject): " + choose(asObject));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ReadVarWithoutIde.java
java ReadVarWithoutIde
```

### Kết quả stdout

```text
codes: [A1, B22, C333]
longCodes: [B22, C333]
length(B22): 3
total length: 9
first B: B22
mixed: [text, 42]
typed: [safe]
empty sizes: 0/0
choose(label): String
choose(asObject): Object
```

### Giải thích tại sao nhận được kết quả ấy

1. `loadCodes()` khai báo rõ kiểu trả về `List<String>`. Chỉ cần đọc chữ ký là xác định `codes` có kiểu `List<String>`, dù không mở IDE.
2. `lengthsOf(List<String>)` trả `Map<String,Integer>`; vì vậy `lengths` cũng là `Map<String,Integer>`. `Map.get("B22")` trả giá trị `3`.
3. `filter` giữ nguyên loại phần tử trong Stream. `Collectors.toUnmodifiableList()` thu được `List<String>` với thứ tự gặp phần tử là `B22, C333`.
4. `findFirst()` trên `Stream<String>` trả `Optional<String>`. Nhánh `orElse("missing")` nhận `B22` trong dữ liệu này.
5. `lengths.values()` là các giá trị `Integer`; `mapToInt(Integer::intValue).sum()` trả `int` bằng `2 + 3 + 4 = 9`. Không cần dựa vào thứ tự duyệt của `Map` để tính tổng.
6. `new ArrayList<>()` trong khai báo `var mixed` thiếu thông tin loại phần tử; kiểu là `ArrayList<Object>` nên thêm cả chuỗi và số nguyên đều hợp lệ. Đây là ví dụ cảnh báo, **không phải khuyến nghị lưu dữ liệu hỗn hợp**.
7. `typed` giữ `List<String>` ở vế trái; `genericEmpty` là `List<Object>`; `typedEmpty` có `List<String>` nhờ type witness. Dòng `List<Object> compileTimeProof = genericEmpty;` giúp xác nhận quan hệ kiểu tĩnh; kích thước `0/0` không tiết lộ generic type qua runtime.
8. `label` có kiểu `String` nên gọi `choose(String)`. `asObject` có kiểu tĩnh `Object` nên gọi `choose(Object)` dù cùng trỏ đến chuỗi `"ready"` lúc chạy.

Không có thứ tự ngẫu nhiên trong output: danh sách `List.of(...)` giữ thứ tự phần tử và Stream trong lab giữ encounter order; code không in thứ tự các khóa của `Map`.

## 5. Đọc bản so sánh thay đổi: các tình huống điển hình

### Tình huống A — Thay kiểu tường minh bằng `var` làm mất generic type

Bản gốc:

```java
List<String> tags = new ArrayList<>();
tags.add("java");
```

Bản sau refactor:

```java
var tags = new ArrayList<>();
tags.add("java");
```

Chỉ nhìn hai dòng có vẻ là “rút ngắn khai báo”. Nhưng bản gốc là `List<String>`, còn bản mới là `ArrayList<Object>`. Dòng `tags.add("java")` vẫn hợp lệ, nên review dựa vào build xanh có thể bỏ sót sự thay đổi hợp đồng.

Ví dụ tiếp theo thể hiện vấn đề:

```java
// Minh họa trong một lớp có phương thức acceptTags(List<String>).
acceptTags(tags); // Bản var ArrayList<Object> không gán được cho List<String>.
```

Cách sửa có chủ đích:

```java
var tags = new ArrayList<String>(); // ArrayList<String>
```

Hoặc giữ nguyên `List<String> tags = new ArrayList<>();` nếu muốn kiểu của biến là interface `List`. Hai lựa chọn trên giữ đúng type argument `String` nhưng **kiểu biến tĩnh vẫn khác nhau** (`ArrayList<String>` so với `List<String>`); điều này có thể ảnh hưởng overload ở các lời gọi sau.

### Tình huống B — Dòng `var` không đổi, nhưng kiểu trả về của hàm thay đổi

Giả sử commit cũ có:

```java
static List<String> loadCodes() {
    return List.of("A1", "B22");
}
```

Và commit mới sửa hợp đồng thành:

```java
static java.util.Collection<String> loadCodes() {
    return List.of("A1", "B22");
}
```

Tại call site:

```java
var codes = loadCodes();
```

dòng khai báo `var` **không có diff**. Tuy nhiên, kiểu tĩnh của `codes` chuyển từ `List<String>` sang `Collection<String>` theo chữ ký mới. Lời gọi `codes.get(0)` hợp lệ trước thay đổi nhưng **không biên dịch** sau đó, vì `Collection` không khai báo `get(int)`.

Đây là lý do đọc một hunks diff đơn lẻ quanh `var` có thể chưa đủ. Hãy đi tới định nghĩa phương thức cùng phiên bản (hoặc Javadoc đã phát hành của thư viện) và rà soát các call site chịu ảnh hưởng.

### Tình huống C — Thay initializer thay đổi primitive type

```diff
- var retryDelay = 10;
+ var retryDelay = 10L;
```

Trong bản cũ, `retryDelay` là `int`; bản mới là `long`. Thay đổi tưởng nhỏ này có thể đổi overload `send(int)`/`send(long)`, lỗi ép kiểu ở nơi dùng biến hoặc kết quả phép toán. Phải đọc **đúng hậu tố literal** và kiểu tĩnh mà JLS suy ra.

Với các phép toán phức tạp hơn, kiểm tra numerical promotion và conversion thay vì suy luận chỉ từ tên biến `retryDelay`.

### Tình huống D — Factory generic không có thông tin từ vế phải

```diff
- List<String> names = Collections.emptyList();
+ var names = Collections.emptyList();
```

Bản cũ có `List<String>` vì target typing; bản mới nhận `List<Object>`. Nếu muốn dùng `var`, viết:

```java
var names = Collections.<String>emptyList();
```

Tương tự, `var result = Optional.empty();` mặc định có thể suy luận `Optional<Object>` khi không có ràng buộc bổ sung. Cần đọc Javadoc và dùng type witness hoặc khai báo tường minh khi kiểu nghiệp vụ không hiển nhiên.

### Tình huống E — Đọc các lời gọi có overload

```java
static String render(Object value) { return "generic"; }
static String render(String value) { return "text"; }

// Trong phương thức:
Object token = "A";
var inferred = "A";
render(token);    // render(Object)
render(inferred); // render(String)
```

Cùng giá trị `"A"` nhưng khác kiểu tĩnh dẫn đến overload khác nhau. Khi review diff đổi `Object token = ...` thành `var token = ...`, phải xem có overload nào phụ thuộc kiểu đối số. Chỉ áp dụng nhận xét này khi đúng các overload tồn tại; đừng suy đoán nếu chưa đọc chữ ký.

## 6. Tài liệu nên đối chiếu theo thứ tự

### 6.1. Javadoc và khai báo API

Với một initializer như `var items = Collections.emptyList();`, thứ tự tra hợp lý là:

1. Tra trang **API của đúng JDK/phiên bản thư viện**.
2. Xem chữ ký generic (`<T> List<T> emptyList()`).
3. Xem các đối số thực tế, type witness và target type ở nơi sử dụng.
4. Suy ra kiểu của **toàn bộ initializer** rồi xác định kiểu `var`.
5. Kiểm tra ràng buộc bổ sung: nullability, mutability, exception contract, thứ tự và lifetime nếu ảnh hưởng nghiệp vụ.

Với các class/method do dự án viết, mở declaration trong cùng commit đang review; tài liệu của phiên bản release khác có thể đã lỗi thời so với source. Nếu chỉ có một trang diff mà không thấy declaration, ghi rõ phần cần kiểm chứng trước khi approve.

### 6.2. JLS để giải quyết trường hợp khó

JLS `14.4.1 định nghĩa cách compiler suy luận kiểu khai báo biến cục bộ `var`. Khi biểu thức có generics hoặc diamond `<>`, cần kết hợp các quy tắc về method invocation (`15.12`), class instance creation (`15.9`) và type inference (`18`). Không cần học thuộc toàn bộ JLS để đọc một PR; chỉ dùng khi trường hợp vượt quá mức có thể suy luận chắc chắn từ API signatures và ví dụ kiểm chứng.

JEP 286 giải thích vì sao local-variable type inference chỉ áp dụng cho phạm vi hẹp, nơi initializer đủ thông tin để duy trì tính dễ đọc. Đây là ngữ cảnh thiết kế giúp người review đánh giá **tính rõ ràng**, ngoài việc code có đúng về mặt compiler hay không.

### 6.3. Chú ý đúng nguồn API, đúng phiên bản

- `List.of(...)` đã được giới thiệu từ Java 9; có thể dùng để truy kiểu khi đọc `var` trong dự án Java 10+ nhưng **không nên ghi nhầm nó là tính năng mới của Java 10**.
- `Collectors.toUnmodifiableList()` và `toUnmodifiableMap(...)` xuất hiện ở Java 10, vẫn được hỗ trợ trên JDK hiện đại.
- `Stream.toList()` được bổ sung **sau Java 10**; nếu gặp nó trong diff hiện đại, tra Javadoc đúng version và không đồng nhất với mọi `Collector` khác.
- Hành vi của một thư viện bên thứ ba có thể thay đổi qua phiên bản. Không áp đặt chữ ký hoặc contract của release hiện tại cho commit cũ.

## 7. Công cụ đọc diff và mã nguồn không cần IDE

Khi có checkout Git hợp lệ và quyền truy cập repository, có thể dùng các lệnh phổ biến sau:

```bash
# So sánh thay đổi với nhánh cơ sở (đổi tên nhánh theo repository).
git diff --unified=8 main...HEAD -- src/main/java

# Xem đầy đủ một tệp ở commit hiện tại.
git show HEAD:src/main/java/com/example/Service.java

# Tìm chữ ký của phương thức trong mã nguồn dự án.
rg -n 'loadCodes\\(' src/main/java

# Xem nơi kiểu trả về, initializer hoặc type argument đã thay đổi.
git diff --word-diff=plain main...HEAD -- src/main/java
```

Các đường dẫn `src/main/java/com/example/Service.java` và tên nhánh `main` **chỉ minh họa** cho cấu trúc một repository điển hình; thay bằng đường dẫn/nhánh thực tế. Nếu dự án không dùng Git hoặc chỉ có giao diện web, dùng phần **Files changed** của pull request và chức năng mở file tại từng commit. Khi grep theo nhiều file, tra cả lớp, interface, hàm generic và các overload liên quan.

Giữ ý thức về phần diff chưa hiển thị: Git có thể rút gọn context mặc định. Mở rộng context, mở nguyên tệp hoặc lần theo hàm được gọi nếu initializer trải nhiều dòng, có import ẩn hoặc kiểu phụ thuộc generic.

Sau khi đối chiếu, nếu có thể chạy:

```bash
javac -Xlint:all ReadVarWithoutIde.java
java ReadVarWithoutIde
```

Compiler phát hiện các lỗi không thể gán kiểu hoặc signature mismatch. `-Xlint:all` cung cấp thêm một số cảnh báo, **nhưng không có nghĩa compiler sẽ cảnh báo mọi trường hợp `var` suy luận thành `Object` ngoài ý muốn**. Đó vẫn là trách nhiệm của review kiểu tĩnh và hợp đồng nghiệp vụ.

### Mẫu ghi chú review có thể hành động được

> Trong diff, `List<String> tags = new ArrayList<>()` được đổi thành `var tags = new ArrayList<>()`. Với initializer mới, kiểu suy luận thành `ArrayList<Object>`, làm mất ràng buộc `String`. Hãy giữ `List<String>` hoặc đổi vế phải thành `new ArrayList<String>()`; sau đó kiểm tra các call site và overload dùng `tags`.

Nhận xét tốt trỏ đúng **dòng mã, kiểu cũ/mới, hệ quả và sửa đổi cụ thể**. Tránh nhận xét chung chung “không được dùng `var`” vì nhiều initializer hoàn toàn rõ ràng và an toàn.

## 8. Những ngộ nhận khi đọc `var` ngoài IDE

| Nhận định dễ sai | Điều đúng cần kiểm tra |
| --- | --- |
| “`var` là kiểu động.” | `var` là suy luận kiểu tĩnh tại biên dịch; không đổi kiểu theo giá trị gán sau đó. |
| “Tên biến `users` chắc là `List<User>`.” | Kiểu lấy từ initializer và chữ ký API, không từ tên biến. |
| “`new ArrayList<>()` luôn biết kiểu từ nơi dùng sau này.” | Với `var`, initializer không nhận target từ vế trái; thường suy luận `Object` khi không có ràng buộc. |
| “Code compile thì refactor `var` an toàn.” | Có thể compile với generic bị rộng thành `Object`, gây mất kiểm tra kiểu. |
| “Kết quả in ra runtime chứng minh generic type.” | Type erasure khiến runtime output không đủ để chứng minh `List<String>` hay `List<Object>`. |
| “`var result = getData()` chắc chắn là `List`.” | Phải tra chữ ký `getData()` tại đúng commit. |
| “Diff không chạm dòng `var`, vậy kiểu không đổi.” | Method return type, generic instantiation hoặc dependency API có thể đổi ở nơi khác. |
| “`var value = null;` hợp lệ như các ngôn ngữ động.” | Không hợp lệ vì `null` đơn lẻ không cung cấp kiểu suy luận. |
| “`var fn = x -> x.toString();` luôn hợp lệ.” | Lambda trực tiếp cần target functional interface; `var` không cung cấp target type đó. |
| “Bất kỳ `var` nào đều khó đọc.” | `var file = new File(path)` hoặc `var names = List.of("A","B")` có thể đủ rõ; cần đánh giá theo initializer và ngữ cảnh. |

Đừng nhầm `var` ở biến cục bộ với dạng khai báo tham số lambda dùng `var` được bổ sung ở Java 11. Đây là một cú pháp có phạm vi khác, không thay đổi quy tắc đọc kiểu biến cục bộ của Java 10 đang đề cập.

## 9. Bài tập đọc mã ngoài IDE

### Bài 1 — Suy ra kiểu từ Javadoc và chữ ký

Cho:

```java
static List<String> getNames() {
    return List.of("An", "Binh");
}

// Trong một phương thức:
var a = getNames();
var b = Collections.emptyList();
var c = Collections.<String>emptyList();
var d = new ArrayList<>(getNames());
```

**Đáp án:** `a` có kiểu `List<String>`; `b` có kiểu `List<Object>` vì không có target từ vế trái; `c` là `List<String>` nhờ type witness; `d` là `ArrayList<String>` vì đối số constructor mang thông tin kiểu `String`. Mục đích là xác định **kiểu tĩnh**, không dựa vào các giá trị danh sách.

### Bài 2 — Tìm sai lệch trong refactor

```diff
- List<String> codes = new ArrayList<>();
+ var codes = new ArrayList<>();
```

**Đáp án:** Bản mới là `ArrayList<Object>`. Thêm `String` có thể vẫn chạy nhưng ràng buộc generic thay đổi; sửa thành `var codes = new ArrayList<String>();` hoặc giữ khai báo ban đầu. Nhớ đánh giá thêm việc kiểu biến tĩnh chuyển từ interface sang concrete type.

### Bài 3 — Dòng không đổi, chữ ký đổi

Một phiên bản hàm trả `List<String>`; phiên bản mới trả `Collection<String>`. Call site giữ `var rows = fetchRows();`. Hỏi `rows.get(0)` còn hợp lệ không?

**Đáp án:** Không còn hợp lệ khi `rows` được suy luận là `Collection<String>`; interface này không định nghĩa `get(int)`. Người review phải xem cả diff chữ ký hàm và các nơi dùng `rows`, dù dòng khai báo `var` không đổi.

### Bài 4 — Xác định loại qua Stream

```java
var lengths = List.of("A", "BBB").stream()
        .map(String::length)
        .collect(Collectors.toUnmodifiableList());
```

**Đáp án:** `List.of(...)` cho `List<String>`; `map(String::length)` tạo `Stream<Integer>`; collector trả `List<Integer>`. `lengths` có kiểu `List<Integer>`. Việc `var` không có target từ vế trái không ngăn method reference nhận target từ tham số `map`.

### Bài 5 — Literal ảnh hưởng overload

```java
static String f(int x) { return "int"; }
static String f(long x) { return "long"; }

// Trong một phương thức:
var a = 1;
var b = 1L;
System.out.println(f(a));
System.out.println(f(b));
```

**Đáp án:** In `int` rồi `long`. Chỉ khác hậu tố `L` nhưng loại biến tĩnh và overload được chọn đã thay đổi. Đây là loại chi tiết dễ lọt khi chỉ xem diff ngắn.

### Bài 6 — Đủ bằng chứng hay chưa?

Cho một diff chỉ có:

```java
var result = repository.findActive();
```

**Đáp án:** Chưa đủ cơ sở xác định kiểu. Phải tìm loại tĩnh của `repository`, chữ ký `findActive()` (kể cả generic type parameters và overload), phiên bản thư viện/source tương ứng. Nếu thiếu, ghi câu hỏi review yêu cầu chữ ký hoặc ngữ cảnh; không điền kiểu theo suy đoán.

## 10. Checklist review `var` ngoài IDE

- [ ] Đọc **trọn initializer** tới dấu chấm phẩy, gồm generic method, lambda, collector và phép cast.
- [ ] Xác định kiểu tĩnh bằng khai báo/Javadoc, không bằng tên biến hoặc giá trị in ra.
- [ ] Tra định nghĩa API **đúng phiên bản** và phương thức nội bộ **đúng commit**.
- [ ] Kiểm tra diamond `<>`, `Collections.emptyList()`, `Optional.empty()` và factory generic khi không có target type.
- [ ] Phân biệt interface, concrete type và generic type arguments sau refactor.
- [ ] Tìm thay đổi liên quan ở các tệp khác: return type, overload, type parameter, dependency.
- [ ] Đọc những call site có thể bị tác động, đặc biệt overload và phương thức chỉ có trên subtype.
- [ ] Kiểm tra sự khác biệt giữa kiểu tĩnh và loại đối tượng thấy ở runtime.
- [ ] Biên dịch/test khi có thể; không coi build xanh là bằng chứng đầy đủ về độ rõ ràng của `var`.
- [ ] Khi đề xuất sửa, nêu chính xác kiểu cũ/kiểu mới, ảnh hưởng và một cách sửa cụ thể.
- [ ] Đối chiếu được 10 dòng stdout của `ReadVarWithoutIde.java`.

## 11. Khi nào nên để `var`, khi nào nên ghi rõ kiểu?

Giữ `var` nếu initializer ngắn và thể hiện đủ rõ kiểu có ý nghĩa cho người đọc, chẳng hạn `var name = "Java";`, `var count = 3;` hoặc `var codes = List.of("A", "B");`. Chọn kiểu tường minh nếu initializer là hàm nội bộ tên mơ hồ, generic factory không mang thông tin type argument, hoặc kết quả của pipeline phức tạp khiến reviewer phải đi qua nhiều tệp để xác định contract.

Với những đoạn mã liên quan an toàn kiểu dữ liệu hoặc lựa chọn overload, giá trị của một khai báo `List<Customer>` hay `Map<Id,Order>` rõ ràng đôi khi lớn hơn số ký tự tiết kiệm từ `var`. Quyết định cuối cùng dựa trên **tính dễ hiểu của mã và hợp đồng API**, không có quy tắc cấm hoặc bắt buộc `var` cho mọi biến.

Kỹ năng cần luyện là tự khôi phục được kiểu tĩnh từ initializer và tài liệu, rồi so sánh kiểu ấy giữa hai phiên bản mã. Đây là kỹ năng còn phù hợp với code review và tài liệu Java hiện đại.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi, mục đích và giới hạn thiết kế của `var`.
- [Java Language Specification — Local Variable Declarations, `14.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): cách suy luận kiểu của khai báo biến cục bộ.
- [Java Language Specification — Method Invocation Expressions, `15.12](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): cách suy luận, kiểm tra lời gọi và overload resolution.
- [Java Language Specification — Type Inference, `18](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html): cơ sở suy luận kiểu với generics.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): cách dùng `var` trên JDK hiện đại.
- [Java SE API — Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html), [List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html) và [Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): tra chữ ký và hợp đồng phương thức khi không có IDE.