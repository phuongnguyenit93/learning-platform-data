# Java 10: Phân biệt tính năng có nguồn gốc ở Java 10 với những mở rộng ở các phiên bản sau

## Mục tiêu học tập

Sau bài này, bạn có thể xác định một đoạn mã đang dùng **khả năng được giới thiệu ở Java 10**, **khả năng xuất hiện trước Java 10**, hay **khả năng bổ sung ở các bản Java mới hơn**. Trọng tâm là những kiến thức vẫn có ích khi viết và bảo trì Java hiện đại: suy luận kiểu biến cục bộ, API collection không cho sửa đổi, `Optional` và mối liên hệ của chúng với các cú pháp/API phát triển về sau.

**Nguyên tắc quan trọng:** Một cú pháp có mặt trong dự án sử dụng JDK 17, 21 hoặc mới hơn không có nghĩa cú pháp đó bắt nguồn từ Java 17/21. Ngược lại, việc Java 10 có `var` **không** có nghĩa Java 10 đã có mọi cách sử dụng `var` được hỗ trợ ngày nay.

## 1. Cách xác định “nguồn gốc” của một tính năng

Hãy phân biệt ba khái niệm:

1. **Xuất hiện ở phiên bản nào:** phiên bản Java đầu tiên cung cấp tính năng/API tương ứng. Ví dụ: suy luận kiểu biến cục bộ bằng `var` là Java 10.
2. **Được mở rộng ở phiên bản nào:** một phiên bản sau cho phép thêm ngữ cảnh sử dụng hoặc cung cấp API mới giải quyết vấn đề gần giống. Ví dụ: `var` trong tham số lambda là Java 11; `Stream.toList()` là Java 16.
3. **Được chuẩn hóa ở phiên bản nào:** một tính năng ngôn ngữ từng ở trạng thái preview có thể chỉ trở thành tính năng chính thức trong bản phát hành sau. Ví dụ: `switch` expression chính thức ở Java 14; pattern matching cho `switch` chính thức ở Java 21.

Khi nói về code có thể dùng lâu dài, bài này lấy **mốc tính năng chính thức (không cần `--enable-preview`)** và các API ổn định. Nếu cần kiểm tra một tính năng có dùng được trên mức Java mục tiêu hay không, hãy biên dịch với `javac --release <phiên-bản>`; việc chỉ nhìn phiên bản của IDE hoặc JDK đang chạy chưa đủ.

## 2. Bản đồ phiên bản: trước Java 10, Java 10 và các bản mở rộng

| Phiên bản | Những điểm vẫn hữu ích hiện nay | Kết luận về nguồn gốc |
|---|---|---|
| **Java 8** | Lambda, method reference, Stream API, `Optional` | Đã có **trước** Java 10; Java 10 không phát minh ra lambda/Stream/Optional. |
| **Java 9** | `List.of` / `Set.of` / `Map.of`, Java Platform Module System, `Optional.stream()` | Factory `of(...)` cho collection và hệ thống module không bắt nguồn từ Java 10. |
| **Java 10** | `var` cho **biến cục bộ có giá trị khởi tạo**; `List.copyOf` / `Set.copyOf` / `Map.copyOf`; `Collectors.toUnmodifiableList/Set/Map`; `Optional.orElseThrow()` không đối số | Đây là các mốc Java 10 cần nhận diện trong code ứng dụng. |
| **Java 11** | `var` trong khai báo tham số lambda; `String.isBlank()`, `strip()`, `lines()`; `Files.readString()` | Mở rộng cách dùng `var` và bổ sung API; không phải nội dung gốc của Java 10. |
| **Java 14** | `switch` expression với `case ... ->` và `yield` | Cú pháp `switch` trả về giá trị chỉ chính thức từ Java 14. |
| **Java 15** | Text block `"""..."""` | Chuỗi nhiều dòng không phải tính năng Java 10. |
| **Java 16** | `record`, pattern matching cho `instanceof`; `Stream.toList()` | Đây là các tính năng/API mới, không phải sự thay đổi ngầm của Java 10. |
| **Java 17** | `sealed` class/interface | Giới hạn tập kiểu được phép kế thừa là mốc Java 17. |
| **Java 21** | Pattern matching cho `switch`; record patterns | Có thể kết hợp `var` với record pattern; tổ hợp này yêu cầu Java 21. |
| **Java 22** | Unnamed variables và unnamed patterns dùng `_` | Dấu `_` để bỏ qua giá trị là tính năng khác với `var` của Java 10. |

Bảng chỉ liệt kê các mốc **đã chính thức hóa** có liên quan đến việc đọc Java hiện đại. Nó không có nghĩa Java 10 chỉ có các thay đổi trên: Java 10 còn có các cải tiến JVM, GC, CDS và quy tắc đánh số phiên bản, nhưng chúng thuộc nhóm vận hành/runtime, không phải cú pháp `var`.

## 3. Những khả năng thực sự xuất phát từ Java 10

### 3.1. `var`: suy luận kiểu biến cục bộ ở thời điểm biên dịch (JEP 286)

Java 10 cho phép viết:

```java
var count = 3;                 // kiểu suy ra là int
var title = "Java";            // kiểu suy ra là String
var names = List.of("Lan");    // kiểu suy ra là List<String>
```

Đây là **đoạn minh họa cần đặt trong một phương thức** và có `import java.util.List;`, không phải một chương trình độc lập.

Trình biên dịch suy ra **kiểu tĩnh** từ biểu thức khởi tạo. Sau khi biên dịch, `var` không tạo ra một kiểu “động” có thể đổi tùy ý. Chẳng hạn, `count` vẫn là `int`; phép gán chuỗi cho `count` sẽ bị từ chối khi biên dịch.

Trong Java 10, `var` có thể dùng cho:
- Biến cục bộ có initializer trong phương thức/khối lệnh;
- Biến khai báo trong phần khởi tạo của vòng `for`;
- Biến duyệt trong enhanced `for`;
- Biến tài nguyên cục bộ trong `try-with-resources` khi có initializer phù hợp.

`var` **không phải kiểu dữ liệu để dùng tùy nơi**. Không thể dùng nó làm kiểu của field, kiểu trả về phương thức hoặc kiểu của tham số phương thức thông thường. Khai báo `var` không có initializer, khởi tạo trực tiếp chỉ bằng `null`, hoặc dùng một lambda đứng một mình mà không có target type cũng không hợp lệ.

Ví dụ về hai giới hạn (cố ý **không biên dịch được**, để nhận biết lỗi):

```java
var unknown = null;       // Không suy ra được kiểu từ null
var number = 10;
number = "mười";          // number là int, không thể gán String
```

**Khi nào nên dùng `var`?** Khi kiểu hiển nhiên từ vế phải và tên biến thể hiện rõ ý nghĩa, chẳng hạn `var users = userRepository.findActiveUsers();` nếu người đọc đã hiểu API. Với biểu thức phức tạp, generic khó nhìn, hoặc khi kiểu mang ý nghĩa thiết kế quan trọng, khai báo tường minh như `List<User> users = ...` thường rõ hơn. `var` chỉ giảm phần chữ lặp lại; không thay thế thiết kế kiểu tốt.

**Cạm bẫy về suy luận generic:** `var items = new ArrayList<>();` thường cho kiểu `ArrayList<Object>` nếu không có ngữ cảnh đích rõ ràng; nếu mong muốn chứa chuỗi, hãy dùng `var items = new ArrayList<String>();` hoặc `List<String> items = new ArrayList<>();`. Suy luận kiểu vẫn dựa vào biểu thức thực tế, không dựa vào ý định ngầm của lập trình viên.

### 3.2. API tạo collection không cho sửa đổi

Java 9 đã có `List.of(...)`, `Set.of(...)`, `Map.of(...)`. **Java 10 bổ sung các API nhận dữ liệu sẵn có**:

- `List.copyOf(Collection)`: tạo một danh sách không cho sửa đổi từ một collection;
- `Set.copyOf(Collection)`: tạo một tập không cho sửa đổi từ một collection;
- `Map.copyOf(Map)`: tạo một map không cho sửa đổi từ một map;
- `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()`, `toUnmodifiableMap()`: gom phần tử của Stream thành collection không cho sửa đổi.

Phân biệt hai tình huống:

- **Tạo từ các phần tử cung cấp trực tiếp:** `List.of("A", "B")` — **Java 9**.
- **Tạo từ collection đã tồn tại:** `List.copyOf(existingList)` — **Java 10**.

`copyOf` tạo một kết quả không phản ánh các thay đổi về **cấu trúc collection nguồn** sau đó; khi đầu vào đã là collection không cho sửa đổi, implementation có thể tái sử dụng instance. Không nên dựa vào `==` để kiểm tra nó có “sao chép” thành object mới hay không.

**Không cho sửa đổi collection không đồng nghĩa bất biến sâu.** Nếu phần tử là đối tượng có trạng thái thay đổi được, thay đổi bên trong phần tử vẫn có thể quan sát được. Các factory này cũng từ chối `null` ở vị trí phần tử/khóa/giá trị tương ứng; với Stream collector `toUnmodifiableMap`, khóa trùng lặp còn cần xử lý theo overload phù hợp.

### 3.3. `Optional.orElseThrow()` không tham số

`Optional` xuất hiện từ Java 8. Java 10 bổ sung overload `orElseThrow()` **không truyền supplier**. Khi có giá trị, phương thức trả về giá trị; khi trống, ném `NoSuchElementException`.

```java
var value = Optional.of("ready").orElseThrow();  // "ready"
```

Đoạn minh họa cần `import java.util.Optional;` và đặt trong thân phương thức. Cần phân biệt overload này với `orElseThrow(Supplier<? extends X>)` đã có từ Java 8; cách truyền supplier cho phép ném ngoại lệ tùy chọn.

### 3.4. Các mốc JVM/runtime của Java 10

Java 10 còn có JEP 307 (**Parallel Full GC for G1**), JEP 310 (**Application Class-Data Sharing**), JEP 312 (**Thread-Local Handshakes**) và JEP 322 (**Time-Based Release Versioning**). Chúng giúp giải thích lịch sử tối ưu JVM và cách ghi phiên bản JDK, nhưng không tạo ra cú pháp Java mới. Cách cấu hình GC, CDS và phân tích hiệu năng phải dựa vào tài liệu của **JDK đang triển khai**, vì implementation tiếp tục phát triển qua các bản sau; không áp dụng máy móc tùy chọn vận hành của năm 2018 vào JVM hiện tại.

## 4. Ví dụ chạy được: chỉ dùng khả năng có từ Java 10 trở về trước

Lưu thành **`Origin10.java`**. Đoạn mã dùng `var` và `copyOf`/`toUnmodifiableList`/`orElseThrow()` của Java 10, cùng `List.of` vốn có từ Java 9.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class Origin10 {
    public static void main(String[] args) {
        var mutableNames = new ArrayList<>(List.of("Lan", "Minh", "An"));
        var snapshot = List.copyOf(mutableNames);

        // Thay đổi danh sách nguồn sau khi tạo snapshot.
        mutableNames.add("Hoa");

        var upper = snapshot.stream()
                .map(String::toUpperCase)
                .collect(Collectors.toUnmodifiableList());

        var selected = Optional.of("Lan").orElseThrow();

        for (var name : snapshot) {
            if (name.length() == 2) {
                System.out.println("short=" + name);
            }
        }

        System.out.println("mutable=" + mutableNames);
        System.out.println("snapshot=" + snapshot);
        System.out.println("upper=" + upper);
        System.out.println("selected=" + selected);
    }
}
```

Biên dịch bằng JDK hiện đại có hỗ trợ target release 10, rồi chạy:

```bash
javac --release 10 Origin10.java
java Origin10
```

Kết quả chuẩn:

```text
short=An
mutable=[Lan, Minh, An, Hoa]
snapshot=[Lan, Minh, An]
upper=[LAN, MINH, AN]
selected=Lan
```

Giải thích: `mutableNames` đã nhận thêm phần tử `Hoa` nhưng `snapshot` không đổi cấu trúc; `upper` là danh sách không cho sửa đổi; các biến `var` đều mang kiểu tĩnh cụ thể. Không có `record`, `switch` expression hay pattern matching của các Java sau trong ví dụ này.

## 5. Những thứ có vẻ “cùng nhóm” nhưng chỉ được bổ sung sau Java 10

### 5.1. Java 11: `var` trong tham số lambda (JEP 323)

`var` ở Java 10 áp dụng cho biến cục bộ. Đến Java 11, nó mới được cho phép trong danh sách tham số của **lambda có target type**. Cú pháp này đặc biệt hữu ích khi muốn gắn annotation cho tham số lambda và muốn viết đồng nhất kiểu khai báo.

Lưu thành **`LambdaVar11.java`**:

```java
import java.util.function.BiFunction;

public class LambdaVar11 {
    public static void main(String[] args) {
        BiFunction<String, String, String> join =
                (var left, var right) -> left + "-" + right;

        System.out.println(join.apply("Java", "11"));
    }
}
```

```bash
javac --release 11 LambdaVar11.java
java LambdaVar11
```

```text
Java-11
```

Kiểu của `left` và `right` vẫn do `BiFunction<String, String, String>` quyết định. Trong cùng danh sách tham số lambda, nếu viết `var` thì **tất cả** tham số phải dùng `var`; không trộn `(var x, y)` hoặc `(var x, String y)`. Mã này **không** hợp lệ với `--release 10`.

### 5.2. Java 14–21: các cú pháp biểu thức và pattern matching mới

Những mốc dễ bị nhầm với khả năng “tự suy ra kiểu” của `var`:

- **Java 14:** `switch` expression chính thức, có thể gán trực tiếp kết quả cho biến và dùng `case ... ->`. Việc **gán** kết quả cho một biến `var` là kết hợp hai tính năng có **nguồn gốc khác nhau** (Java 10 + Java 14).
- **Java 16:** `record` là cách khai báo kiểu dữ liệu ngắn gọn; `instanceof String s` vừa kiểm tra kiểu vừa ràng buộc biến pattern `s`. Đây không phải là mở rộng `var` ban đầu.
- **Java 17:** `sealed interface/class` giới hạn các lớp được phép triển khai/kế thừa.
- **Java 21:** pattern matching trong `switch` và record patterns chính thức. Dạng `case Success(var code)` là **record pattern**, không phải cú pháp có thể dùng chỉ vì Java 10 đã hỗ trợ `var`.
- **Java 22:** `_` để biểu thị biến/pattern không sử dụng là tính năng mới, khác hoàn toàn với `var`.

Ví dụ tổng hợp sau yêu cầu **Java 21+**, tuyệt đối không gắn nhãn “ví dụ Java 10”.

Lưu thành **`Modern21.java`**:

```java
sealed interface Message permits Success, Failure {}

record Success(int code) implements Message {}
record Failure(String reason) implements Message {}

public class Modern21 {
    public static void main(String[] args) {
        var status = 200;                       // var: Java 10
        var label = switch (status) {           // switch expression: Java 14
            case 200 -> "OK";
            default -> "OTHER";
        };

        Object raw = "Java";
        if (raw instanceof String s) {         // pattern instanceof: Java 16
            System.out.println("length=" + s.length());
        }

        Message msg = new Success(7);          // sealed + record: Java 17/16
        String text = switch (msg) {           // pattern switch: Java 21
            case Success(var code) -> "success=" + code;
            case Failure(var reason) -> "failure=" + reason;
        };

        System.out.println("status=" + label);
        System.out.println(text);
    }
}
```

```bash
javac --release 21 Modern21.java
java Modern21
```

```text
length=4
status=OK
success=7
```

Có thể thấy **cùng một chương trình** dùng các ngôn ngữ tính năng có mốc bắt đầu khác nhau. Mức Java tối thiểu của **toàn chương trình** là mức cao nhất trong các tính năng nó sử dụng; ở đây là Java 21.

### 5.3. Java 16: `Stream.toList()` không phải API Java 10

Với Stream, Java 10 cung cấp:

```java
var result = stream.collect(Collectors.toUnmodifiableList());
```

Đoạn minh họa giả định biến `stream` phù hợp và có import `java.util.stream.Collectors`.

Từ **Java 16**, có thể dùng:

```java
var result = stream.toList();
```

Hai cách đều có thể tạo danh sách không cho sửa đổi, nhưng **không cùng phiên bản xuất hiện** và không nên mặc nhiên xem các đặc tính hợp đồng API của chúng là giống hệt (đặc biệt khi xử lý `null` hoặc tính chất implementation). Nếu code cần tương thích Java 10, `Stream.toList()` không phải lựa chọn hợp lệ; dùng collector được Java 10 hỗ trợ hoặc một phương án thích hợp khác.

### 5.4. Phân biệt “cách viết ngắn” với “tính năng cùng nguồn”

Mẫu tư duy đúng:

| Đoạn mã | Tính năng cấu thành | Java tối thiểu |
|---|---|---|
| `var n = 10;` | Local-variable type inference | **10** |
| `var xs = List.of("a");` | `var` (10) + `List.of` (9) | **10** |
| `List.copyOf(existing);` | Copy factory | **10** |
| `stream.collect(Collectors.toUnmodifiableList())` | Unmodifiable collector | **10** |
| `(var x, var y) -> x + y` | Lambda parameter syntax kiểu `var` | **11** |
| `var name = switch (code) { case 1 -> "one"; default -> "other"; };` | `var` (10) + `switch` expression (14) | **14** |
| `obj instanceof String s` | Type pattern cho `instanceof` | **16** |
| `stream.toList()` | Terminal operation của Stream | **16** |
| `record Point(int x, int y) {}` | Record class | **16** |
| `sealed interface Shape permits Circle {}` | Sealed types (cần định nghĩa `Circle` hợp lệ) | **17** |
| `case Success(var code) -> ...` | Record pattern trong pattern switch | **21** |

Các ô có `stream`, `existing`, `code` hoặc `obj` là **mảnh cú pháp để phân loại**, cần khai báo ngữ cảnh nếu muốn biên dịch độc lập. Mốc tối thiểu ở bảng phản ánh cú pháp/API được nêu, không bao gồm mã bao quanh.

## 6. Những nhầm lẫn thường gặp và cách sửa

1. **“Java 10 tạo ra tất cả lambda/Stream/Optional.”** Sai: ba nhóm này bắt đầu từ Java 8; Java 10 chỉ bổ sung một số API liên quan như collector không cho sửa đổi và overload của `Optional`.
2. **“`List.of` là Java 10.”** Sai: `List.of` có từ Java 9; `List.copyOf` mới là Java 10.
3. **“`var` là kiểu động như trong một số ngôn ngữ scripting.”** Sai: kiểu biến được xác định khi biên dịch và vẫn được Java kiểm tra tĩnh.
4. **“Có `var` là mọi vị trí bỏ kiểu đều hợp lệ.”** Sai: Java 10 giới hạn ở biến cục bộ phù hợp; cú pháp cho tham số lambda được mở rộng từ Java 11.
5. **“`var` có thể khởi tạo bằng `null` không cần thông tin bổ sung.”** Sai: thiếu thông tin để suy ra kiểu.
6. **“Collection tạo qua `copyOf` luôn có object identity mới.”** Sai: kết quả có thể tái sử dụng đối tượng không cho sửa đổi thích hợp; chỉ dựa vào hợp đồng API.
7. **“Collection không cho sửa đổi thì mọi object bên trong đều bất biến.”** Sai: `copyOf` không thực hiện sao chép sâu.
8. **“`Collectors.toUnmodifiableList()` và `Stream.toList()` cùng được giới thiệu ở Java 10.”** Sai: tương ứng Java 10 và Java 16.
9. **“`case Success(var code)` chạy với Java 10 vì có từ `var`.”** Sai: đây là record pattern bên trong pattern matching `switch`, ổn định ở Java 21.
10. **“Chạy ứng dụng bằng JDK mới thì nguồn gốc tính năng cũng là JDK đó.”** Sai: phân biệt phiên bản xuất hiện của tính năng, phiên bản target khi biên dịch và phiên bản runtime thực tế.

## 7. Cách tự kiểm chứng khả năng tương thích

Dùng một JDK hiện đại hỗ trợ các mức `--release` tương ứng và kiểm tra từng file độc lập:

```bash
javac --release 10 Origin10.java
java Origin10

javac --release 11 LambdaVar11.java
java LambdaVar11

javac --release 21 Modern21.java
java Modern21
```

- `--release N` yêu cầu trình biên dịch kiểm tra cú pháp ngôn ngữ và API thư viện chuẩn tương ứng với **Java N**, đồng thời tạo bytecode phù hợp mức đó. Nó giúp phát hiện việc vô tình sử dụng API đến từ bản Java muộn hơn.
- Cờ này **không** biến một JVM cũ thành JVM mới và cũng không chứng minh mọi thư viện phụ thuộc bên ngoài tương thích. Khi triển khai còn phải kiểm tra runtime, dependency, build tool và bộ kiểm thử thực tế.
- Thử thay `--release 11` của `LambdaVar11.java` thành `--release 10` sẽ thấy cú pháp `var` trong lambda không được Java 10 chấp nhận. Tương tự, `Modern21.java` yêu cầu tối thiểu Java 21 vì dùng pattern `switch`/record patterns chính thức ở phiên bản đó.
- Khi xem tài liệu API, trường **Since** là một dấu hiệu đáng tin về mốc xuất hiện. Khi xem cú pháp ngôn ngữ, đối chiếu bảng **Java Language Changes** hoặc JEP và phân biệt rõ **preview** với **standard**.

## 8. Câu hỏi tự kiểm tra

1. `var score = 42;` là Java mấy? **Java 10** — biến cục bộ, suy luận kiểu tĩnh `int`.
2. `var people = List.of("A", "B");` có phải hai tính năng cùng sinh ra ở Java 10 không? **Không** — `List.of` là Java 9, `var` là Java 10; cả biểu thức cần Java 10 trở lên.
3. Java nào đầu tiên hỗ trợ `(var left, var right) -> left + right` trong lambda có target type phù hợp? **Java 11**.
4. `Optional.of(value).orElseThrow()` không tham số có từ phiên bản nào? **Java 10**.
5. `names.stream().toList()` có chạy khi biên dịch với `--release 10` không? **Không** — phương thức này có từ **Java 16**.
6. `var result = switch (code) { ... };` có thể gắn nhãn “Java 10” không? **Không** — nếu dùng `switch` expression chính thức, tối thiểu **Java 14**.
7. `case Point(var x, var y) -> ...` trong pattern `switch` có thuộc Java 10? **Không** — record pattern/pattern `switch` chính thức ở **Java 21**.
8. `List.copyOf(mutable)` có bảo vệ khỏi việc sửa các thuộc tính của đối tượng phần tử không? **Không** — nó không sao chép sâu các phần tử.

## 9. Tài liệu chính thức để đối chiếu

- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): bảng xuất hiện của `var`, lambda `var`, `switch`, record, pattern và sealed types.
- [Oracle — JDK 10 Release Notes](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): các bổ sung Java 10 cho `Optional`, collection factory/collector và các cải tiến JVM.
- [Oracle — `List` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): xem `Since: 9` của `of`, `Since: 10` của `copyOf` và hợp đồng unmodifiable.
- [Oracle — `Stream` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): xem `Since: 16` của `toList()`.
- [OpenJDK — JEP 286](https://openjdk.org/jeps/286): suy luận kiểu biến cục bộ ở Java 10.
- [OpenJDK — JEP 323](https://openjdk.org/jeps/323): mở rộng `var` trong lambda từ Java 11.
- [Oracle — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html): tổng hợp các mốc ngôn ngữ mới hơn.

**Ghi nhớ:** Java 10 cung cấp `var` **cho biến cục bộ**, nhóm `copyOf`, các `toUnmodifiable...` collector và `Optional.orElseThrow()` không đối số. Các khả năng như `var` trong lambda, `switch` expression, `record`, pattern matching và `Stream.toList()` phải gán đúng **mốc phát hành sau Java 10**.