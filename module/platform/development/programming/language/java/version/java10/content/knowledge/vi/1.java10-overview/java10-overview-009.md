# Thực hành các kiến thức Java 10 trên JDK còn được hỗ trợ

> **Phạm vi:** Ôn và áp dụng những khả năng được giới thiệu trong Java 10 mà vẫn hữu ích trên JDK hiện đại. Bài thực hành dùng cú pháp và API chuẩn, không yêu cầu cài JDK 10 hay sử dụng tính năng thử nghiệm/cơ chế triển khai đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dùng `var` cho biến cục bộ khi kiểu đã rõ từ biểu thức khởi tạo; giải thích được kiểu suy luận ở **thời điểm biên dịch**.
2. Tạo bản chụp collection không cho phép thay đổi qua `List.copyOf`, `Set.copyOf` và `Map.copyOf`; phân biệt bản chụp với một view chỉ đọc.
3. Xử lý Stream thành kết quả không cho phép sửa bằng `Collectors.toUnmodifiableList/Set/Map`.
4. Lấy giá trị bắt buộc từ `Optional` bằng `orElseThrow()` không đối số và xử lý trường hợp thiếu dữ liệu.
5. Chạy một chương trình tổng hợp, kiểm chứng output và nhận diện các giới hạn `null`, phần tử trùng, phần tử bên trong vẫn có thể thay đổi.

## 2. Chuẩn bị môi trường

Sử dụng **một JDK LTS đang được nhà cung cấp của bạn hỗ trợ và cập nhật bản vá**; ví dụ, JDK 21 hoặc JDK 25 từ bản phân phối còn bảo trì. Không cần quay về JDK 10 để luyện tập. Tại thời điểm soạn bài (11/2026), cả 21 và 25 có các bản phân phối LTS đang được hỗ trợ; vòng đời và điều khoản cấp phép cụ thể phụ thuộc nhà cung cấp.

Mở terminal, kiểm tra compiler và runtime:

```bash
java -version
javac -version
```

Cả hai lệnh phải hoạt động và trỏ đến JDK phù hợp. Nếu `javac` không được tìm thấy, kiểm tra việc cài **JDK** (không chỉ runtime), `JAVA_HOME` và `PATH`. Dùng một cửa sổ terminal mới sau khi chỉnh biến môi trường.

Bài dùng Java chuẩn, không cần Maven, Gradle hay thư viện ngoài. Lưu toàn bộ chương trình bên dưới thành **`Java10Practice.java`**, đúng với tên `public class`. Từ thư mục chứa tệp, chạy:

```bash
javac Java10Practice.java
java Java10Practice
```

Lệnh `javac` biên dịch ra `Java10Practice.class`; lệnh `java` chạy tên lớp **không có đuôi `.class`**. Ví dụ sử dụng API có từ Java 10 trở về trước, nên không đòi tính năng ngôn ngữ mới hơn Java 10 dù chạy bằng JDK đang hỗ trợ.

## 3. Các điểm Java 10 cần thực hành

| Khả năng | Có từ | Dùng để làm gì hôm nay? |
| --- | --- | --- |
| Suy luận kiểu biến cục bộ `var` | Java 10 | Giảm việc lặp kiểu dài khi vế phải đã cho biết kiểu rõ ràng. |
| `List.copyOf`, `Set.copyOf`, `Map.copyOf` | Java 10 | Tạo bản chụp collection không cho phép thay đổi; hữu ích khi trao dữ liệu qua ranh giới hàm/lớp. |
| `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()`, `toUnmodifiableMap(...)` | Java 10 | Chuyển Stream thành kết quả không cho phép thêm/xóa/sửa phần tử của collection. |
| `Optional.orElseThrow()` không đối số | Java 10 | Bắt buộc có giá trị, nếu trống thì ném `NoSuchElementException`. |

Lưu ý về mốc phiên bản: `List.of`/`Set.of`/`Map.of` đã có từ **Java 9**, còn `Stream.toList()` xuất hiện sau Java 10. Chúng có thể gặp trong mã hiện đại nhưng không được tính là đóng góp riêng của Java 10. Cũng không nhầm `var` với một kiểu dữ liệu mới: kiểu của biến vẫn là kiểu Java tĩnh.

## 4. Lab hoàn chỉnh: quản lý tập số và snapshot bất biến

Tạo tệp **`Java10Practice.java`** với toàn bộ nội dung sau:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

public class Java10Practice {
    public static void main(String[] args) {
        // 1) var: compiler suy luận ArrayList<Integer> từ vế phải.
        var source = new ArrayList<>(List.of(5, 8, 10, 12));

        // 2) Snapshot Java 10 khác với view chỉ đọc.
        var snapshot = List.copyOf(source);
        var view = Collections.unmodifiableList(source);
        source.add(14);

        // 3) Collectors Java 10, không dựa vào thứ tự của Set/Map.
        var even = snapshot.stream()
                .filter(n -> n % 2 == 0)
                .collect(Collectors.toUnmodifiableList());
        var unique = snapshot.stream()
                .collect(Collectors.toUnmodifiableSet());
        var squares = snapshot.stream()
                .collect(Collectors.toUnmodifiableMap(n -> n, n -> n * n));

        // 4) Set.copyOf và Map.copyOf giữ dữ liệu thời điểm tạo.
        var frozenSet = Set.copyOf(snapshot);
        var settings = new HashMap<String, String>();
        settings.put("mode", "safe");
        var copiedSettings = Map.copyOf(settings);
        settings.put("mode", "fast");

        // 5) Optional.orElseThrow() không đối số, có từ Java 10.
        var first = snapshot.stream()
                .filter(n -> n > 9)
                .findFirst()
                .orElseThrow();

        System.out.println("Snapshot: " + snapshot);
        System.out.println("Source: " + source);
        System.out.println("View: " + view);
        System.out.println("Even: " + even);
        System.out.println("Unique has 8: " + unique.contains(8));
        System.out.println("Set.copyOf has 8: " + frozenSet.contains(8));
        System.out.println("Square of 10: " + squares.get(10));
        System.out.println("Copied mode: " + copiedSettings.get("mode"));
        System.out.println("First > 9: " + first);

        try {
            snapshot.add(99);
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot: no mutation");
        }

        try {
            Optional.<Integer>empty().orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("Optional: no value");
        }

        try {
            List.copyOf(Arrays.asList("A", null));
        } catch (NullPointerException ex) {
            System.out.println("List.copyOf: rejects null");
        }
    }
}
```

### Output mong đợi

```text
Snapshot: [5, 8, 10, 12]
Source: [5, 8, 10, 12, 14]
View: [5, 8, 10, 12, 14]
Even: [8, 10, 12]
Unique has 8: true
Set.copyOf has 8: true
Square of 10: 100
Copied mode: safe
First > 9: 10
Snapshot: no mutation
Optional: no value
List.copyOf: rejects null
```

Output cố ý **không in trực tiếp nội dung `Set` hoặc `Map`**: thứ tự duyệt của các collection không cho phép sửa được tạo từ các factory/copy/collector này không phải cam kết để viết test. Truy cập theo khóa hoặc `contains` giúp phép kiểm tra xác định, có thể lặp lại.

### Phân tích kết quả

**Bước 1 — `var`:** `source` được suy luận là `ArrayList<Integer>`. Compiler biết rõ kiểu khi kiểm tra lời gọi `add`, `stream` và các phương thức khác; `var` không cho phép thay đổi kiểu biến khi chạy. `snapshot` là kiểu `List<Integer>`, `even` là `List<Integer>`, `unique` là `Set<Integer>` và `squares` là `Map<Integer,Integer>` dù khai báo không viết lại tên các kiểu này.

**Bước 2 — bản chụp và view:** `snapshot` chứa bốn số lúc gọi `List.copyOf(source)`. Khi thêm `14` vào `source`, snapshot vẫn có bốn số. `Collections.unmodifiableList(source)` chỉ tạo lớp bọc không cho phép sửa **qua view**, nhưng phản ánh thay đổi trên danh sách gốc. Vì vậy `view` xuất hiện số `14`. Đây là khác biệt quan trọng khi trả về dữ liệu có thể bị caller giữ tham chiếu.

**Bước 3 — Stream:** `Collectors.toUnmodifiableList()` giữ thứ tự encounter của Stream ở ví dụ này, nên `even` là `[8, 10, 12]`. `toUnmodifiableSet()` khử trùng và không bảo đảm thứ tự duyệt. `toUnmodifiableMap()` tạo map từ mỗi số sang bình phương; khóa `10` ứng với `100`. Cả ba kết quả không cho phép sửa cấu trúc qua các phương thức cập nhật.

**Bước 4 — copy collection:** `Set.copyOf(snapshot)` tạo tập không cho sửa; nếu nguồn có giá trị trùng nhau, tập chỉ giữ giá trị phân biệt. `Map.copyOf(settings)` bảo toàn cặp `mode=safe` tại thời điểm sao chép; thay đổi `settings` thành `fast` không cập nhật bản sao.

**Bước 5 — `Optional`:** Nếu có số lớn hơn `9`, `findFirst()` trả `Optional<Integer>` có giá trị và `orElseThrow()` trả phần tử đầu tiên là `10`. Nếu không có, bản không đối số ném `NoSuchElementException`; chương trình bắt đúng exception này để minh họa nhánh thất bại.

**Bước 6 — trường hợp biên:** thêm vào `snapshot` ném `UnsupportedOperationException`. `List.copyOf` từ danh sách chứa `null` ném `NullPointerException`; xử lý lỗi này ở biên nhận dữ liệu thay vì giả định null được chấp nhận.

## 5. Quy tắc dùng `var` cho dễ đọc

`var` dùng cho biến cục bộ có biểu thức khởi tạo, biến trong vòng lặp `for`, enhanced `for` và biến resource trong `try-with-resources`. Nó không thay `var` cho thuộc tính lớp, tham số phương thức hay kiểu trả về. Không thể suy luận từ `null` đơn lẻ hoặc từ lambda không có kiểu đích.

Ví dụ ngắn đặt **bên trong một phương thức**:

```java
var count = 3;                         // int
var names = new ArrayList<String>();   // ArrayList<String>
for (var name : List.of("Lan", "Minh")) {
    System.out.println(name);
}
```

Các ví dụ sau **không biên dịch** và được đưa ra để nhận diện lỗi, không sao chép vào chương trình chạy:

```java
// var missing = null;   // Không có kiểu để suy luận.
// var x;                // Thiếu initializer.
// var x = 1; x = "A";  // x đã là int, không thể gán String.
// class Demo { var id = 1; } // Không dùng var để khai báo field.
```

Cẩn thận với `var items = new ArrayList<>();`: khi không có ngữ cảnh generic thích hợp, biểu thức có thể được suy luận thành `ArrayList<Object>`. Nếu phần tử cần kiểu rõ ràng, viết `new ArrayList<String>()` hoặc khai báo rõ `List<String> items = new ArrayList<>();`. Sử dụng `var` khi tên biến và vế phải đủ làm rõ ý định; một khai báo kiểu tường minh đôi khi dễ bảo trì hơn.

## 6. Các bẫy thực tế với collection không cho sửa

### 6.1 Không cho sửa cấu trúc không đồng nghĩa bất biến sâu

`List.copyOf` tạo một collection không cho thêm, xóa hoặc thay phần tử **qua API List**. Nếu phần tử bên trong là đối tượng mutable, nội dung đối tượng ấy vẫn thay đổi được. Đoạn sau đặt **trong phương thức** để quan sát:

```java
var builder = new StringBuilder("A");
var copied = List.copyOf(List.of(builder));
builder.append("B");
System.out.println(copied.get(0)); // AB
```

Khi cần dữ liệu thật sự bất biến, thiết kế phần tử bất biến hoặc tạo bản sao sâu theo cấu trúc dữ liệu của ứng dụng. Không dựa vào danh tính đối tượng do `copyOf` trả về; một implementation có thể tái sử dụng collection đầu vào nếu đầu vào đã không cho phép sửa.

### 6.2 Null và khóa trùng

`List.copyOf`, `Set.copyOf`, `Map.copyOf` không chấp nhận phần tử null (với `Map` là khóa và giá trị null). Bộ `Collectors.toUnmodifiable*` cũng từ chối kết quả ánh xạ null. Với dữ liệu ngoài ứng dụng, hãy kiểm tra/lọc/chuẩn hóa null trước khi tạo collection.

`Collectors.toUnmodifiableMap(keyMapper, valueMapper)` sẽ ném `IllegalStateException` nếu hai phần tử tạo cùng khóa. Khi nghiệp vụ cho phép gộp, truyền hàm merge tường minh:

```java
// Đoạn ví dụ trong phương thức:
var words = List.of("aa", "ab", "c");
var countByFirstChar = words.stream()
        .collect(Collectors.toUnmodifiableMap(
                s -> s.charAt(0),
                s -> 1,
                Integer::sum));
System.out.println(countByFirstChar.get('a')); // 2
```

Hãy chọn cách gộp theo yêu cầu nghiệp vụ; không tự ý giữ một giá trị khi dữ liệu trùng biểu thị lỗi. `Set.copyOf` thì có ngữ nghĩa khác: nó loại giá trị trùng chứ không báo lỗi vì trùng.

### 6.3 Snapshot, wrapper và Stream collector nên chọn khi nào?

| Tình huống | Lựa chọn | Điểm cần nhớ |
| --- | --- | --- |
| Đã có `List`, cần bản chụp độc lập với thay đổi cấu trúc ở nguồn | `List.copyOf(source)` | Bản chụp nông; không phản ánh thêm/xóa ở nguồn. |
| Cần tập giá trị phân biệt từ collection | `Set.copyOf(source)` | Không dựa vào thứ tự duyệt. |
| Cần ánh xạ chỉ đọc từ map hiện có | `Map.copyOf(source)` | Khóa/giá trị null không hợp lệ. |
| Đang `filter`/`map` Stream, cần đầu ra không cho sửa | `Collectors.toUnmodifiableList/Set/Map` | Xử lý null và khóa trùng theo contract. |
| Chủ đích cần view phản ánh thay đổi nguồn | `Collections.unmodifiableList(source)` | Không thể sửa qua view, nhưng nguồn vẫn có thể thay đổi. |

Tên gọi “immutable collection” thường được dùng trong tài liệu, nhưng khi giải thích chính xác, hãy hiểu các collection ở đây **unmodifiable ở cấu trúc** và snapshot theo mô tả từng API.

## 7. Bài tập tự làm và tiêu chí hoàn thành

**Bài A — suy luận kiểu và snapshot.** Thay `source` thành `new ArrayList<>(List.of(2, 3, 3, 6))` và giữ nguyên đoạn tạo `snapshot`, `view`, rồi thêm `14` vào nguồn. Trước khi chạy, dự đoán từng danh sách; xác nhận snapshot không thêm `14` và view có `14`. Dùng `Set.copyOf(snapshot)` để giải thích số phần tử phân biệt là **3**, không cần in thứ tự tập hợp. Giải thích vì sao không thể gán một `String` cho biến `var` vốn suy luận `ArrayList<Integer>`.

**Bài B — collector bất biến.** Từ `List.of(1, 2, 2, 3, 4, 5)`, dùng Stream tạo danh sách bình phương của số chẵn bằng `toUnmodifiableList()`. Kết quả phải là `[4, 4, 16]` theo thứ tự gặp phần tử. Thử `result.add(36)`, bắt `UnsupportedOperationException` và giải thích vì sao giá trị trùng vẫn còn trong `List`. Chuyển sang `toUnmodifiableSet()` để loại trùng, nhưng chỉ kiểm tra `size()` và `contains()` thay vì thứ tự.

**Bài C — Map và lỗi trùng khóa.** Từ `List.of("an", "anh", "binh")`, thử thu thập thành map với khóa là ký tự đầu và giá trị là độ dài chuỗi. Dự đoán ngoại lệ khi không có merge function; sau đó chọn một quy tắc gộp rõ ràng (ví dụ giữ độ dài lớn nhất qua `Integer::max`) và kiểm tra khóa `'a'` cho kết quả **3**.

**Bài D — Optional.** Tìm một số lớn hơn `100` trong `snapshot`. Với `orElseThrow()`, xử lý `NoSuchElementException` và in thông điệp dễ hiểu. Nếu muốn báo lỗi có ngữ cảnh trong code nghiệp vụ, có thể dùng overload `orElseThrow(() -> new IllegalArgumentException("Không thấy dữ liệu phù hợp"))`; overload nhận supplier này đã tồn tại trước Java 10, nên không coi nó là tính năng mới của Java 10.

### Checklist tự kiểm tra

- [ ] Biên dịch/chạy thành công bằng JDK còn được nhà cung cấp hỗ trợ, không phụ thuộc JDK 10.
- [ ] Giải thích đúng rằng `var` là suy luận kiểu ở compile time và nhận diện trường hợp không hợp lệ.
- [ ] Phân biệt snapshot `copyOf` với view `unmodifiableList` qua một thay đổi nguồn thực tế.
- [ ] Tạo được ít nhất một `List`, `Set` và `Map` không cho sửa bằng API Java 10.
- [ ] Không phụ thuộc thứ tự duyệt `Set`/`Map`; xử lý rõ null, khóa trùng và tính bất biến nông.
- [ ] Thử được cả nhánh có và không có giá trị của `Optional.orElseThrow()`.

## 8. Hướng áp dụng trong dự án

Khi nhận danh sách hoặc map từ nơi khác (cấu hình, repository, service), kiểm tra dữ liệu rồi tạo `copyOf` nếu cần ngăn thay đổi cấu trúc nguồn ảnh hưởng tới dữ liệu đã phát hành. Trong pipeline Stream, dùng `toUnmodifiable*` nếu caller phải nhận kết quả chỉ đọc. Dùng `Optional.orElseThrow()` khi theo contract buộc phải tìm thấy giá trị, hoặc overload có supplier để đưa ra lỗi miền nghiệp vụ rõ hơn. Với `var`, ưu tiên ở phạm vi cục bộ và chỉ khi kiểu suy luận đủ hiển nhiên cho người đọc.

Những ví dụ trên tập trung vào tính năng Java 10 **vẫn sử dụng được trên JDK được hỗ trợ**; không hướng dẫn cài runtime Java 10 hết vòng đời, không dựa vào tùy chọn máy ảo hay API thử nghiệm của bản phát hành cũ.

## Tài liệu chuẩn để đối chiếu

- [Oracle Java Language Updates – Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html) — phạm vi và giới hạn của `var`.
- [Oracle JDK 10 – Creating Immutable Lists, Sets, and Maps](https://docs.oracle.com/javase/10/core/creating-immutable-lists-sets-and-maps.htm) — `copyOf`, snapshot và collectors.
- [Java 10 API – Optional](https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html) — `orElseThrow()` không đối số.
- [Microsoft Build of OpenJDK – Support roadmap](https://learn.microsoft.com/en-us/java/openjdk/support) — tra vòng đời hỗ trợ của các JDK LTS theo nhà cung cấp.