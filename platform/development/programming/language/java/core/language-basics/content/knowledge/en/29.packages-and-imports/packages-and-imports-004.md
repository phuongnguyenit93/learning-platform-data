# Import một kiểu và import theo yêu cầu bằng dấu `*` — Java 17+

## 1. `import` giải quyết vấn đề gì?

Mỗi kiểu Java thuộc một package (trừ kiểu ở *unnamed package*). Khi sử dụng kiểu nằm ngoài package hiện tại, ta có thể viết **tên đầy đủ** (*fully qualified name*) hoặc dùng `import` để viết **tên ngắn** trong mã nguồn.

~~~java
java.util.List<String> names = java.util.List.of("An", "Binh");
~~~

Tương đương khi khai báo import phù hợp:

~~~java
import java.util.List;

// Trong một lớp:
List<String> names = List.of("An", "Binh");
~~~

`import` giúp **tra cứu tên lúc biên dịch**, không tạo object, không tự chạy mã của lớp được import và không sao chép mã nguồn thư viện vào file.

## 2. Hai cú pháp cần nhận diện

| Cú pháp | Tên gọi | Ý nghĩa |
|---|---|---|
| `import java.util.List;` | **Single-type-import declaration** | Cho phép dùng tên ngắn `List` cho **một kiểu cụ thể** |
| `import java.util.*;` | **Type-import-on-demand declaration** | Cho phép dùng tên ngắn của **các kiểu truy cập được** trong package `java.util` khi cần phân giải tên |
| `java.util.List.of(...)` | Tên kiểu đầy đủ, không phải import | Không cần khai báo import cho `List` |
| `import static java.lang.Math.PI;` | Single-static-import | Import **thành viên static**; khác với import kiểu |
| `import static java.lang.Math.*;` | Static-import-on-demand | Import thành viên static theo yêu cầu; không phải `import java.lang.Math.*;` |

Dấu `*` trong `import java.util.*;` **không có nghĩa** sao chép hay khởi tạo toàn bộ các lớp trong package. Trình biên dịch chỉ sử dụng các khai báo import để phân giải những tên xuất hiện trong mã.

Ở Java 17, chỉ có ký hiệu `*` **nguyên vẹn** ở cuối khai báo import-on-demand: không có cú pháp kiểu `import java.util.L*;` để lọc tiền tố.

## 3. Dấu `*` không tìm kiếm đệ quy package con

`import java.util.*;` cho phép dùng các kiểu truy cập được trực tiếp từ `java.util` như `List` và `Map`, nhưng không tự đưa `java.util.concurrent.TimeUnit` vào phạm vi tên ngắn:

~~~java
long seconds = java.util.concurrent.TimeUnit.MINUTES.toSeconds(1); // 60
~~~

Muốn dùng `TimeUnit` không có tiền tố, hãy khai báo `import java.util.concurrent.TimeUnit;`. Bài về package con phân tích thêm các kiểu `AtomicInteger`, `Method` và sự khác biệt giữa package con với kiểu lồng nhau.

## 4. Khi nào dùng tên ngắn và tên đầy đủ?

~~~java
import java.util.List;

List<String> a = List.of("A");
java.util.List<String> b = java.util.List.of("B");
~~~

Cả hai đều sử dụng kiểu `java.util.List`.

- Dùng **single-type import** khi chỉ cần một vài kiểu: dễ nhận biết chính xác dependency.
- Dùng **import-on-demand** khi làm việc với nhiều kiểu trong cùng package: ít dòng import hơn nhưng khó thấy ngay tất cả kiểu đang dùng.
- Dùng **tên đầy đủ** khi cần nói rõ kiểu nào giữa các kiểu trùng tên, hoặc ở chỗ chỉ xuất hiện một lần.
- IDE thường tự thêm, gộp hoặc sắp xếp import; đây là lựa chọn trình bày mã, không làm thay đổi hành vi bản thân kiểu được sử dụng.

**Cả hai dạng import đều không làm thay đổi tính năng của `List` hoặc cấu trúc của object**. Khác biệt chủ yếu ở việc phân giải tên.

## 5. Khi hai package có kiểu cùng tên

~~~java
import java.util.List;
import java.awt.*;

// Trong lớp:
List<String> names = List.of("An"); // java.util.List
~~~

Single-type import cụ thể xác định `List` dù wildcard còn có `java.awt.List`. Với hai wildcard `java.util.*` và `java.awt.*`, tên `List` có thể trở nên mơ hồ; hai single-type imports khác kiểu cùng tên đơn giản thì gây lỗi ngay tại khai báo import. Java không có quy tắc “import cuối thắng”. Dùng qualified name khi phải nói rõ kiểu; bài xử lý hai lớp trùng tên đi sâu vào mức ưu tiên.

## 6. Import kiểu lồng nhau và `java.lang`

Một kiểu lồng (*member type*) có thể import trực tiếp:

~~~java
import java.util.Map.Entry;

// Trong lớp:
Entry<String, Integer> item =
        java.util.Map.entry("An", 10);
~~~

`Entry` là kiểu lồng của `Map`; ở đây `Map.entry(...)` được viết bằng tên đầy đủ của `Map` vì ví dụ chỉ import `Entry`.

Một số kiểu thông dụng như `String`, `System`, `Integer`, `Math` thuộc `java.lang`, và các kiểu truy cập được trong `java.lang` được Java **import-on-demand ngầm định**; thường không phải viết `import java.lang.String;`.

Kiểu được khai báo trong **cùng package** cũng có thể dùng tên ngắn khi không bị che khuất/xung đột theo quy tắc của Java.

## 7. Vị trí đặt `package` và `import`

Thứ tự thường thấy của một file `.java`:

~~~java
package demo;

import java.util.List;
import java.time.*;

public class Example {
    // ...
}
~~~

1. Khai báo `package` (nếu có), sau các chú thích và khoảng trắng.
2. Các khai báo `import`, trước mọi top-level type declaration.
3. Các khai báo `class`, `record`, `interface`, `enum`... của file.

Không đặt `import` bên trong thân một phương thức hoặc sau một khai báo top-level class. Dấu `;` là bắt buộc cuối mỗi khai báo `package`/`import`.

Một file chỉ được có **tối đa một khai báo package**. Tên package không phải là đường dẫn file tự động do `import` tạo; lúc chạy, classpath và tên lớp đầy đủ vẫn phải phù hợp với file `.class` được biên dịch.

## 8. Chương trình Java 17+ chạy độc lập

Tạo một file tên **`ImportKindsDemo.java`** trong thư mục làm việc, với toàn bộ nội dung:

~~~java
package demo;

import java.util.List;       // Import đúng một kiểu.
import java.util.*;          // Các kiểu khác trong java.util khi cần.
import java.time.*;          // Package khác, import-on-demand riêng.
import java.util.Map.Entry;  // Kiểu lồng cụ thể.

public final class ImportKindsDemo {
    private ImportKindsDemo() {}

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        ArrayList<String> copy = new ArrayList<>(names);
        copy.add("Chi");

        LocalDate date = LocalDate.of(2026, 10, 16);
        Map<String, Integer> scores = Map.of(
                "An", 10, "Binh", 20);
        Entry<String, Integer> pair = Map.entry("Chi", 30);

        System.out.println("names=" + names);
        System.out.println("copy=" + copy);
        System.out.println("date=" + date);
        System.out.println("score An=" + scores.get("An"));
        System.out.println("entry=" + pair.getKey() + ":" + pair.getValue());

        System.out.println("max=" + Collections.max(copy));
        System.out.println("length=" + "Java".length());
        System.out.println("qualified="
                + java.util.List.of("X", "Y").size());
        System.out.println("time unit="
                + java.util.concurrent.TimeUnit.MINUTES.toSeconds(2));
    }
}
~~~

Cách đọc các dòng import: `List` được chọn qua khai báo cụ thể; `ArrayList`, `Map`, `Collections` qua `java.util.*`; `LocalDate` qua `java.time.*`; `Entry` qua import kiểu lồng; `String` là `java.lang.String` được biết ngầm định; `TimeUnit` được dùng bằng **tên đầy đủ**, không cần import `java.util.concurrent`.

**Biên dịch** từ thư mục chứa `ImportKindsDemo.java`. Tùy chọn `-d .` đặt file `.class` vào thư mục package phù hợp (`demo/`); không bắt buộc sắp sẵn thư mục nguồn `demo` để chạy ví dụ đơn file này.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 -d . ImportKindsDemo.java
java -cp . demo.ImportKindsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 -d . .\ImportKindsDemo.java
java -cp . demo.ImportKindsDemo
~~~

### Exact expected stdout

~~~text
names=[An, Binh]
copy=[An, Binh, Chi]
date=2026-10-16
score An=10
entry=Chi:30
max=Chi
length=4
qualified=2
time unit=120
~~~

Đầu ra không phụ thuộc thứ tự duyệt `Map.of`, vì chương trình **chỉ lấy phần tử theo khóa** `"An"`, không in trực tiếp toàn bộ map. Không cần `--enable-preview`.

## 9. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| `import java.util.*;` rồi nghĩ đã có `TimeUnit` | Không bao gồm subpackage `concurrent` | Import riêng hoặc dùng tên đầy đủ |
| `import java.util.L*;` | Không phải cú pháp Java | `import java.util.List;` hoặc `import java.util.*;` |
| Import cả `java.util.*` và `java.awt.*`, rồi dùng `List` | Hai kiểu trùng tên gây mơ hồ | Single-type import hoặc qualified name |
| Hai single-type imports cho hai `List` khác nhau | Xung đột khai báo | Chỉ import một, kiểu kia dùng tên đầy đủ |
| Đặt `import` trong `main` | Import chỉ nằm ở đầu compilation unit | Đặt sau `package`, trước class |
| Nghĩ wildcard import class vào runtime ngay | Import là cơ chế phân giải tên lúc biên dịch | Không suy luận tải lớp từ cú pháp import |
| Nghĩ `java.lang.String` luôn phải import | Có import-on-demand ngầm định cho `java.lang` | Dùng `String` trực tiếp |
| Gọi `java Demo` khi class ở `package demo` | Thiếu tên nhị phân đầy đủ | `java -cp . demo.ImportKindsDemo` |
| Nhầm `import static` với import kiểu | Một bên import thành viên static | Chọn đúng cú pháp theo thứ được sử dụng |

## 10. Bài tập có đáp án

**A.** Viết import chỉ dành cho `ArrayList` thuộc package `java.util`.  
**Đáp án:** `import java.util.ArrayList;`

**B.** Có `import java.time.*;`, có dùng trực tiếp `LocalDate` được không?  
**Đáp án:** **Có**, vì `LocalDate` thuộc package `java.time`.

**C.** Có `import java.util.*;`, có dùng trực tiếp `TimeUnit` không?  
**Đáp án:** **Không**, vì `TimeUnit` thuộc `java.util.concurrent`; thêm `import java.util.concurrent.TimeUnit;` hoặc ghi tên đầy đủ.

**D.** Với `import java.util.List;` và `import java.awt.*;`, `List` không định danh đầy đủ chọn kiểu nào?  
**Đáp án:** `java.util.List`, theo khai báo single-type import cụ thể.

**E.** Không import `List`, có khai báo `java.util.List<String> names;` được không?  
**Đáp án:** **Có**, dùng tên đầy đủ nên không cần import.

**F.** Import `java.util.*` có khiến Java nạp hết lớp ở package đó khi khởi động không?  
**Đáp án:** **Không**; wildcard import tham gia phân giải tên trong compilation unit, không ra lệnh nạp tất cả lớp.

## 11. Checklist và kết luận

- [ ] Phân biệt single-type import `import a.b.Type;` với type-import-on-demand `import a.b.*;`.
- [ ] Biết wildcard `*` không bao gồm package con, không lọc theo tiền tố.
- [ ] Biết dùng fully qualified type name khi không muốn import.
- [ ] Nhận diện trường hợp trùng simple name và import mơ hồ.
- [ ] Không coi thứ tự các dòng import là thứ tự ưu tiên.
- [ ] Phân biệt import kiểu và `import static`.
- [ ] Hiểu vị trí `package`, `import`, top-level type trong file.
- [ ] Hiểu `java.lang` được import-on-demand ngầm định.
- [ ] Biết `javac -d .` và tên `package.Class` khi chạy chương trình đóng gói.
- [ ] Biên dịch, chạy `ImportKindsDemo.java` trên JDK 17+, kiểm tra exact stdout.

**Kết luận:** `import package.Type;` đưa **một kiểu cụ thể** vào khả năng dùng tên ngắn; `import package.*;` cho phép phân giải **các kiểu truy cập được trong đúng package ấy** khi cần. Dấu `*` không import đệ quy package con và không tự nạp tất cả lớp; khi trùng tên, dùng single-type import rõ ràng hoặc tên kiểu đầy đủ.