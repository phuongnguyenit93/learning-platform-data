# Phân biệt static import với import kiểu

Hai khai báo sau đều giúp viết tên ngắn hơn, nhưng đưa **hai loại tên khác nhau** vào quá trình phân giải mã nguồn:

```java
import java.util.Collections;
import static java.util.Collections.emptyList;
```

Dòng thứ nhất cho phép viết tên kiểu `Collections` thay cho `java.util.Collections`. Dòng thứ hai cho phép viết tên phương thức `emptyList` thay cho `Collections.emptyList` trong ngữ cảnh phù hợp.

Muốn chọn đúng, hãy hỏi: **mình đang muốn rút gọn tên một kiểu hay tên một thành viên static?**

## 1. Đặt hai cơ chế cạnh nhau

| Tiêu chí | Import kiểu | Static import |
| --- | --- | --- |
| Từ khóa | `import` | `import static` |
| Đối tượng tên được nhập | Kiểu: class, interface, enum, annotation, record... | Thành viên static truy cập được: trường, phương thức, kiểu thành viên static |
| Ví dụ | `import java.util.Collections;` | `import static java.util.Collections.emptyList;` |
| Cách dùng sau import | `Collections.emptyList()` | `emptyList()` |
| Có nhập các tên phương thức vào phạm vi dưới dạng tên đơn giản không? | Không, chỉ bởi việc nhập kiểu | Có, đối với tên phương thức static được nhập |
| Có tự nhập tên kiểu chứa thành viên không? | Kiểu được chỉ định là mục tiêu của import | Không |
| Có tạo đối tượng không? | Không | Không |
| Có bỏ qua quyền truy cập không? | Không | Không |

Bảng này tập trung vào khai báo nhập tên cụ thể. Khi dùng dấu `*`, vẫn cần phân biệt nhập kiểu với nhập thành viên static; dấu sao không xóa ranh giới đó.

## 2. Import kiểu: rút gọn phần tên kiểu

Không có import kiểu, có thể dùng tên đầy đủ:

```java
java.util.List<String> names = java.util.Collections.emptyList();
```

Sau khi thêm:

```java
import java.util.Collections;
import java.util.List;
```

có thể viết trong thân phương thức:

```java
List<String> names = Collections.emptyList();
```

Những gì thay đổi là cách viết `List` và `Collections`. Tên phương thức vẫn đi sau kiểu chứa nó: `Collections.emptyList()`.

Chỉ nhập `Collections` không đủ để gọi `emptyList()` bằng tên đơn giản. Nếu tệp không có một nguồn tên phù hợp khác, lời gọi đó không biên dịch.

Tương tự, nhập một lớp để dùng phương thức instance không tạo sẵn đối tượng:

```java
import java.util.ArrayList;

// Trong thân phương thức:
ArrayList<String> names = new ArrayList<>();
names.add("Java");
```

Import giúp dùng tên kiểu `ArrayList`; biểu thức `new ArrayList<>()` mới tạo đối tượng. `add` vẫn được gọi trên đối tượng `names`.

## 3. Static import: rút gọn phần tên thành viên

Thêm khai báo:

```java
import static java.util.Collections.emptyList;
```

rồi có thể gọi:

```java
List<String> names = emptyList();
```

Đoạn này giả định `List` cũng đã được nhập hoặc được viết bằng tên đầy đủ.

Import không chuyển phương thức vào lớp đang viết, không tạo một phương thức mới và không thiết lập quan hệ kế thừa. Phương thức được gọi vẫn là phương thức static của `Collections`.

Với trường static, ý tưởng tương tự:

```java
import static java.util.concurrent.TimeUnit.SECONDS;

// Trong thân phương thức:
long milliseconds = SECONDS.toMillis(2);
```

`SECONDS` là hằng enum của `TimeUnit`. Thành viên được nhập là trường đó; `toMillis` vẫn là phương thức instance gọi trên giá trị enum. Static import không đòi hỏi toàn bộ chuỗi lời gọi sau tên được nhập phải là static.

Một import phương thức ghi tên, không ghi chữ ký:

```java
import static java.lang.Math.max;
```

Các overload truy cập được cùng tên có thể được xét tại lời gọi. Import không chọn trước `max(int, int)` hay `max(double, double)`.

## 4. Hai chương trình, cùng kết quả

Hai ví dụ sau độc lập, đều dùng cú pháp và API áp dụng trong Java hiện hành. Chạy bằng JDK 17 trở lên.

### Cách 1: nhập kiểu và giữ tiền tố kiểu

Lưu thành `TypeImportExample.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class TypeImportExample {
    public static void main(String[] args) {
        List<String> names = Collections.emptyList();
        long milliseconds = TimeUnit.SECONDS.toMillis(2);

        System.out.println("size: " + names.size());
        System.out.println("milliseconds: " + milliseconds);
    }
}
```

### Cách 2: nhập thành viên static

Lưu thành `StaticImportExample.java`:

```java
import static java.util.Collections.emptyList;
import static java.util.concurrent.TimeUnit.SECONDS;

import java.util.List;

public class StaticImportExample {
    public static void main(String[] args) {
        List<String> names = emptyList();
        long milliseconds = SECONDS.toMillis(2);

        System.out.println("size: " + names.size());
        System.out.println("milliseconds: " + milliseconds);
    }
}
```

Đặt hai tệp cùng một thư mục, biên dịch và chạy:

```shell
javac -encoding UTF-8 TypeImportExample.java StaticImportExample.java
java TypeImportExample
java StaticImportExample
```

Mỗi lệnh `java` in cùng stdout:

```text
size: 0
milliseconds: 2000
```

Khi chạy liên tiếp cả hai lệnh như trên, hai dòng đó xuất hiện hai lần.

Ví dụ thứ hai không nhập tên kiểu `Collections` hoặc `TimeUnit`. Nó không cần hai tên kiểu ấy vì thân chương trình chỉ dùng các thành viên đã được nhập. Cả hai ví dụ vẫn phải có tên kiểu `List` để khai báo biến, nên cả hai đều nhập `java.util.List`.

Không có sự khác biệt chức năng do đổi cơ chế import trong hai chương trình này; chúng gọi cùng API với cùng đối số.

## 5. Những suy luận sai thường gặp

### “Nhập lớp là nhập luôn tất cả phương thức của nó”

```java
import java.util.Collections;

// Trong phương thức:
// List<String> names = emptyList(); // Chưa có tên emptyList phù hợp.
```

Nếu muốn dùng tên ngắn `emptyList`, hãy nhập chính tên static đó. Nếu muốn nhìn thấy nguồn tại chỗ gọi, dùng `Collections.emptyList()`.

### “Nhập thành viên là đã nhập luôn lớp chứa nó”

```java
import static java.util.concurrent.TimeUnit.SECONDS;

// Trong phương thức:
long delay = SECONDS.toMillis(2);
// TimeUnit unit = SECONDS; // Cần phân giải tên kiểu TimeUnit riêng.
```

Nếu cần khai báo biến `TimeUnit`, thêm `import java.util.concurrent.TimeUnit;` hoặc dùng tên đầy đủ. Hai loại import có thể cùng tồn tại khi mỗi loại giải quyết một nhu cầu.

### “Mọi thứ sau import thông thường đều có thể là trường hoặc phương thức”

Khai báo sau không nhập được trường hằng số:

```java
// Cố ý minh họa import không hợp lệ:
// import java.lang.Math.PI;
```

Đích của single-type import phải là một kiểu; `PI` là trường. Muốn dùng tên ngắn của trường này, cần `import static java.lang.Math.PI;`.

Tương tự, `import static java.util.Collections;` không phải cách nhập cả lớp `Collections`: cú pháp single static import cần xác định kiểu chứa và tên thành viên static.

### “Static import có thể biến phương thức instance thành static”

Không. `List.size()` là phương thức instance. Nhập kiểu `List` không làm nó thành static; static import cũng không thay thế đối tượng danh sách cần để gọi `size()`.

Trong hai chương trình trên, `names.size()` vẫn cần đối tượng `names`, bất kể `emptyList` đã được viết theo cách nào.

## 6. Kiểu lồng là điểm giao nhau cần nhớ

Không thể phân loại chỉ bằng việc “tên đó nằm bên trong một lớp”.

`Map.Entry` là kiểu thành viên static, nên có thể dùng import kiểu:

```java
import java.util.Map.Entry;
```

hoặc static import:

```java
import static java.util.Map.Entry;
```

Mỗi cách đều có thể làm tên kiểu `Entry` dùng được trong tệp. Với nhu cầu nhập một kiểu lồng, import kiểu thông thường thường thể hiện mục đích rõ ràng.

Điểm phân biệt đúng là:

- Import kiểu chỉ định một **kiểu**.
- Static import chỉ định một **thành viên static**; thành viên đó có thể chính là một kiểu lồng static.

Do đó, “import kiểu dùng cho class, static import chỉ dùng cho hàm” là mô tả thiếu chính xác. Trường, hằng enum và kiểu lồng static cũng thuộc phạm vi của static import khi đáp ứng điều kiện truy cập.

## 7. Phạm vi và những gì import không làm

Cả hai loại import nằm sau khai báo `package` nếu có, và trước các khai báo kiểu trong tệp. Không đặt chúng vào thân lớp hoặc phương thức.

Chúng tác động đến cách phân giải tên trong đơn vị biên dịch chứa khai báo, thường là một tệp `.java`. Viết import ở một tệp không cấp tên ngắn tương ứng cho mọi tệp cùng thư mục.

Cả hai đều không:

- Tải thư viện từ Internet hoặc khai báo dependency thay cho Gradle.
- Sao chép mã triển khai vào lớp đang viết.
- Tạo đối tượng hay tự gọi một phương thức.
- Vượt qua quyền truy cập `private`, giới hạn package hoặc ranh giới module.

Thư viện vẫn phải có trong môi trường biên dịch/chạy phù hợp. Import chỉ giải quyết cách tham chiếu tên sau khi các kiểu và thành viên thực sự khả dụng.

Một điểm dễ nhầm là các kiểu public trong `java.lang` đã có thể dùng bằng tên ngắn theo quy tắc import ngầm. Điều đó cho phép viết `Math.max(1, 2)` mà không nhập `Math` riêng, nhưng không tự cho phép viết `max(1, 2)`. Tên phương thức vẫn cần nguồn phân giải thích hợp, chẳng hạn static import.

## 8. Chọn cách viết theo khả năng đọc

| Mục đích | Cách thường phù hợp |
| --- | --- |
| Dùng kiểu trong khai báo biến, generic hoặc tạo đối tượng | Import kiểu |
| Muốn nguồn phương thức hiện ngay tại lời gọi | Import kiểu rồi viết `Type.member` |
| Dùng một vài thành viên static quen thuộc, lặp lại nhiều lần | Static import có chọn lọc |
| Tên thành viên quá chung hoặc dễ nhầm nguồn | Giữ tên kiểu chứa thành viên |
| Cần cả tên kiểu và một tên static ngắn | Dùng cả hai khi chúng đều có ích |

Tên ngắn hơn chỉ có giá trị nếu người đọc vẫn hiểu rõ ý định. Khi đọc `emptyList()`, `SECONDS` hoặc một tên kiểm thử quen thuộc, static import có thể giúp mã gọn. Với những tên như `run`, `get` hoặc `create`, tiền tố kiểu có thể cung cấp ngữ cảnh cần thiết.

## 9. Tự kiểm tra

1. `import java.util.Collections;` có đủ để dùng trực tiếp `emptyList()` không?
2. `import static java.util.Collections.emptyList;` có tự cho phép dùng tên kiểu `Collections` không?
3. Vì sao vẫn cần nhập `List` trong chương trình dùng `emptyList()`?
4. `Map.Entry` có thể được nhập bằng import kiểu không dù nó là static?
5. Hai loại import có thay thế cấu hình dependency của Gradle không?

Đáp án:

1. Không; import này đưa tên kiểu `Collections` vào cách phân giải tên ngắn.
2. Không.
3. `List` là tên kiểu được dùng riêng trong khai báo biến.
4. Có; nó là một kiểu, và cũng là một thành viên static nên static import cũng có thể áp dụng.
5. Không; import không tải hoặc cấu hình thư viện.

## Tài liệu đối chiếu

Xem [JLS 21 §7.5.1 — Single-Type-Import Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.1) và [§7.5.3 — Single-Static-Import Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.3). Hai chương trình dùng [Collections.emptyList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#emptyList()) và [TimeUnit.toMillis](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html#toMillis(long)).
