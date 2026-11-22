# Quy tắc truy cập và phân giải tên khi dùng static import

## 1. Hai câu hỏi khác nhau: được truy cập và đang chỉ tới đâu?

Một tên ngắn như `LIMIT` hay `choose(...)` chỉ sử dụng được khi Java trả lời được hai câu hỏi:

1. Thành viên tương ứng có được phép truy cập từ vị trí này không?
2. Nếu có nhiều khai báo liên quan đến cùng tên, khai báo nào được chọn?

Static import giúp đưa thành viên static vào phạm vi sử dụng bằng tên ngắn. Nó **không nâng quyền truy cập**, không ưu tiên theo thứ tự dòng import và không loại bỏ quy tắc che khuất tên hay chọn phương thức nạp chồng.

Hai nhóm lỗi cũng khác nhau:

- **Không truy cập được hoặc không tìm thấy tên:** nguồn import không hợp lệ, thành viên không có quyền truy cập, hoặc không có khai báo phù hợp trong phạm vi.
- **Tên mơ hồ:** có nhiều ứng viên hợp lệ nhưng không xác định được một lựa chọn duy nhất.

Phân biệt hai nhóm này giúp sửa đúng nguyên nhân thay vì thêm import hoặc đổi thứ tự các dòng một cách thử vận may. Bài dùng mã Java 17+ và các quy tắc vẫn áp dụng trên Java hiện hành.

## 2. Chuẩn bị hai lớp nguồn cho các thí nghiệm

Các ví dụ dùng package có tên. Tạo hai tệp sau trong thư mục `demo/api`.

Tệp `demo/api/Symbols.java`:

```java
package demo.api;

public class Symbols {
    public static final int LIMIT = 10;
    static final int LOCAL_LIMIT = 20;
    protected static final int PROTECTED_LIMIT = 30;
    private static final int SECRET = 40;

    public static String choose(int value) {
        return "int:" + value;
    }

    public static String choose(String value) {
        return "text:" + value;
    }
}
```

Tệp `demo/api/OtherSymbols.java`:

```java
package demo.api;

public class OtherSymbols {
    public static final int LIMIT = 99;

    public static String choose(long value) {
        return "long:" + value;
    }

    public static String choose(String value) {
        return "other:" + value;
    }
}
```

Từ thư mục chứa `demo`, biên dịch các lớp nguồn trước:

```shell
javac --release 17 -Xlint:all -Werror -d out demo/api/Symbols.java demo/api/OtherSymbols.java
```

Các lệnh ở những phần sau sử dụng `out` làm classpath và thư mục kết quả. Các chương trình minh họa là những tệp riêng; không ghép nhiều phần `package`/import thành một tệp.

## 3. Static import vẫn tuân theo quyền truy cập

Để nhập một thành viên, trước hết phải truy cập được kiểu chứa thành viên. Một trường `public static` nằm trong một kiểu không truy cập được cũng không tự trở thành một API có thể nhập từ mọi nơi.

Với lớp `Symbols` ở trên:

| Thành viên | Từ lớp khác cùng package `demo.api` | Từ lớp thông thường ở package `demo` |
|---|---|---|
| `public static LIMIT` | Có thể nhập | Có thể nhập |
| `static LOCAL_LIMIT` không có modifier truy cập | Có thể nhập | Không thể nhập |
| `protected static PROTECTED_LIMIT` | Có thể nhập | Không thể nhập chỉ nhờ static import |
| `private static SECRET` | Không thể nhập từ một lớp cấp cao nhất khác | Không thể nhập |

“Cùng package” nghĩa là đúng cùng tên package. `demo`, `demo.api` và `demo.api.internal` là ba package khác nhau; quan hệ tên có dấu chấm không tạo quyền truy cập theo kiểu cha–con.

Quy tắc truy cập tổng quát được mô tả trong [JLS §6.6](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.6); static import còn đòi hỏi kiểu và thành viên được nhập phải đáp ứng điều kiện của [JLS §7.5.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.3).

### Ví dụ cùng package

Tệp `demo/api/SamePackageDemo.java`:

```java
package demo.api;

import static demo.api.Symbols.LOCAL_LIMIT;
import static demo.api.Symbols.PROTECTED_LIMIT;

public class SamePackageDemo {
    public static void main(String[] args) {
        System.out.println(LOCAL_LIMIT);
        System.out.println(PROTECTED_LIMIT);
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/api/SamePackageDemo.java
java -cp out demo.api.SamePackageDemo
```

Kết quả:

```text
20
30
```

Hai trường được nhập vì vị trí import thuộc cùng package với lớp khai báo chúng.

### Ví dụ khác package không hợp lệ

Đoạn sau là một tệp có chủ đích **không biên dịch**:

```java
package demo;

import static demo.api.Symbols.LOCAL_LIMIT;
import static demo.api.Symbols.PROTECTED_LIMIT;
import static demo.api.Symbols.SECRET;

class BadAccess {
}
```

Các import đều không có quyền truy cập tương ứng. Tùy trình biên dịch, chẩn đoán có thể nêu tên không tìm thấy thay vì mô tả trực tiếp modifier; không vì thế mà kết luận trường chưa tồn tại.

Một import theo dấu `*` chỉ đưa vào những thành viên static truy cập được. Chẳng hạn, `import static demo.api.Symbols.*;` từ package `demo` không tự cấp quyền dùng `LOCAL_LIMIT` hay `SECRET`. Đừng hiểu dấu `*` là bỏ qua hàng rào truy cập.

### Trường hợp protected ngoài package

Lớp con ngoài package có thể dùng thành viên protected trong ngữ cảnh được phép của lớp con. Ví dụ hợp lệ:

Tệp `demo/ProtectedDemo.java`:

```java
package demo;

public class ProtectedDemo extends demo.api.Symbols {
    public static void main(String[] args) {
        System.out.println(PROTECTED_LIMIT);
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/ProtectedDemo.java
java -cp out demo.ProtectedDemo
```

Kết quả:

```text
30
```

Tên `PROTECTED_LIMIT` ở đây được dùng như thành viên kế thừa trong thân lớp con; chương trình không cần static import.

Ngược lại, thêm dòng sau ở phần import của tệp lớp con vẫn không hợp lệ:

```java
// Không hợp lệ từ package demo:
// import static demo.api.Symbols.PROTECTED_LIMIT;
```

Khai báo import nằm ngoài thân lớp con, nên không lấy quyền truy cập protected trong thân lớp con để nhập thành viên từ package khác. Việc có `extends Symbols` ở phía dưới không làm dòng import đó hợp lệ.

Với named module, còn phải xét quan hệ đọc module và package được export. Static import không thay thế `requires` hoặc `exports`.

## 4. Phân giải tên trường: khai báo gần có thể che tên được nhập

**Che khuất tên (shadowing)** là tình huống một khai báo trong phạm vi đang xét khiến tên ngắn không còn chỉ tới khai báo khác cùng tên.

Tệp `demo/FieldResolutionDemo.java`:

```java
package demo;

import static demo.api.Symbols.LIMIT;

public class FieldResolutionDemo {
    static final int LIMIT = 7;

    public static void main(String[] args) {
        int LIMIT = 3;
        System.out.println(LIMIT);
        System.out.println(FieldResolutionDemo.LIMIT);
        System.out.println(demo.api.Symbols.LIMIT);
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/FieldResolutionDemo.java
java -cp out demo.FieldResolutionDemo
```

Kết quả:

```text
3
7
10
```

Cách phân giải:

1. `LIMIT` trong `main` chỉ tới biến cục bộ có giá trị 3.
2. `FieldResolutionDemo.LIMIT` chỉ rõ trường của lớp đang viết, có giá trị 7.
3. `demo.api.Symbols.LIMIT` chỉ rõ trường ở lớp nguồn import, có giá trị 10.

Nếu bỏ biến cục bộ `LIMIT`, tên ngắn trong phương thức sẽ tìm được trường `LIMIT` của `FieldResolutionDemo`, không phải trường được nhập. Đặt static import không làm nó có ưu tiên cao hơn khai báo trường ở lớp đang viết.

Dùng tên có chủ sở hữu là cách chọn chính xác trường muốn đọc. Import không xóa hoặc thay đổi các trường còn lại.

Quy tắc che khuất tên nằm trong [JLS §6.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.4.1). Không áp dụng máy móc một bảng ưu tiên tên trường cho mọi trường hợp chọn phương thức.

## 5. Trường nhập tường minh và trường nhập bằng dấu *

Tệp `demo/ImportResolutionDemo.java`:

```java
package demo;

import static demo.api.Symbols.LIMIT;
import static demo.api.OtherSymbols.*;

public class ImportResolutionDemo {
    public static void main(String[] args) {
        System.out.println(LIMIT);
        System.out.println(choose(1L));
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/ImportResolutionDemo.java
java -cp out demo.ImportResolutionDemo
```

Kết quả:

```text
10
long:1
```

Cả hai lớp nguồn đều có trường `LIMIT`, nhưng trường `Symbols.LIMIT` được nhập tường minh bằng tên thành viên. Nó che trường cùng tên được đưa vào qua import dấu `*` của `OtherSymbols`.

Lời gọi `choose(1L)` sử dụng phương thức static từ `OtherSymbols`, được đưa vào qua dấu `*`. Trường `LIMIT` và phương thức `choose` phải được phân giải riêng theo ngữ cảnh của mỗi tên.

Đổi thứ tự hai dòng import không đổi kết quả. Đây là quy tắc phân giải tên, không phải “dòng khai báo sau ghi đè dòng trước”.

### Hai nguồn cùng cung cấp một trường thì sao?

Đoạn sau có chủ đích không biên dịch tại chỗ dùng `LIMIT`:

```java
package demo;

import static demo.api.Symbols.LIMIT;
import static demo.api.OtherSymbols.LIMIT;

class AmbiguousField {
    int value = LIMIT;
}
```

Không có cơ sở chọn giữa hai trường khác nhau. Sửa bằng cách chỉ giữ một import cần thiết hoặc viết rõ:

```java
int first = demo.api.Symbols.LIMIT;
int second = demo.api.OtherSymbols.LIMIT;
```

Nếu dùng hai import dấu `*` cùng đưa vào hai trường này, tên ngắn `LIMIT` cũng mơ hồ khi không có một khai báo khác giải quyết nó.

Đối với các **trường** trong ví dụ, chỉ có hai dòng import mà chưa dùng tên `LIMIT` thì vẫn có thể biên dịch. Đừng nhầm với quy tắc xung đột import của tên kiểu. Chính việc tham chiếu đến tên ngắn mơ hồ mới làm đoạn thí nghiệm trên thất bại.

Một tên bị che khuất cũng không phải cùng tình huống với tên mơ hồ: che khuất có thể chọn được một khai báo; mơ hồ nghĩa là vẫn còn nhiều lựa chọn không phân định được.

## 6. Phương thức: chọn tên rồi chọn overload

Một phương thức được nhập bằng tên không có nghĩa mọi lời gọi tên đó đều trỏ tới cùng một chữ ký. Java còn phải xét số lượng và kiểu đối số để chọn overload thích hợp.

Tệp `demo/OverloadImportDemo.java` dùng hai import tường minh cho tên phương thức `choose`:

```java
package demo;

import static demo.api.Symbols.choose;
import static demo.api.OtherSymbols.choose;

public class OverloadImportDemo {
    public static void main(String[] args) {
        System.out.println(choose(1));
        System.out.println(choose(1L));
        System.out.println(demo.api.Symbols.choose("A"));
        // System.out.println(choose("A")); // Mơ hồ.
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/OverloadImportDemo.java
java -cp out demo.OverloadImportDemo
```

Kết quả:

```text
int:1
long:1
text:A
```

Phân tích các lời gọi trong chính tập import này:

| Lời gọi | Cách chọn |
|---|---|
| `choose(1)` | Chọn `Symbols.choose(int)`; đối số có kiểu `int` |
| `choose(1L)` | Chọn `OtherSymbols.choose(long)`; đối số có kiểu `long` |
| `demo.api.Symbols.choose("A")` | Tên có chủ sở hữu chỉ rõ tìm ở `Symbols` |
| `choose("A")` nếu bỏ dấu comment | Mơ hồ giữa hai phương thức `choose(String)` từ hai lớp |

Kết quả của `choose(1)` không được quyết định bởi dòng import nào viết trước. Phương thức nhận `int` phù hợp hơn phương thức cần mở rộng đối số thành `long`.

Ở `choose("A")`, cả hai lớp đều cung cấp một phương thức static truy cập được có tham số `String`. Không có lựa chọn phù hợp hơn để phân biệt chúng, nên trình biên dịch báo mơ hồ.

Không dùng kiểu của biến nhận kết quả để “chỉ định lớp nguồn”. Cách rõ ràng là gọi `Symbols.choose(...)` hoặc `OtherSymbols.choose(...)`, sau khi import kiểu nếu muốn rút ngắn tên kiểu.

Quá trình xác định phương thức ứng viên và chọn overload được mô tả trong [JLS §15.12](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12). Các ví dụ ở đây tập trung vào kiểu đối số thông thường, không triển khai toàn bộ quy tắc generic, lambda hoặc varargs.

## 7. Phương thức cùng tên trong lớp có thể che phương thức được nhập

Tệp `demo/OwnMethodDemo.java`:

```java
package demo;

import static java.lang.Math.max;

public class OwnMethodDemo {
    static int max(String value) {
        return value.length();
    }

    public static void main(String[] args) {
        System.out.println(max("Java"));
        System.out.println(Math.max(1, 2));
        // System.out.println(max(1, 2)); // Không biên dịch.
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror -cp out -d out demo/OwnMethodDemo.java
java -cp out demo.OwnMethodDemo
```

Kết quả:

```text
4
2
```

`max("Java")` chọn phương thức `max(String)` khai báo trong lớp. Lời gọi `Math.max(1, 2)` chỉ rõ kiểu chứa phương thức nên vẫn dùng được phương thức của JDK.

Nếu bỏ comment ở `max(1, 2)`, mã không biên dịch. Phương thức `max` của lớp làm che tên phương thức được nhập trong phạm vi này. Trình biên dịch không thấy phương thức tại lớp phù hợp rồi tự quay về `Math.max` như một phương án dự phòng.

Đây là lý do cần phân biệt:

- **Overload:** nhiều phương thức cùng tên được xét trong tập ứng viên hợp lệ, rồi chọn theo quy tắc lời gọi.
- **Che khuất tên theo phạm vi:** một khai báo làm nguồn được import không còn tham gia như người viết kỳ vọng.
- **Mơ hồ:** có nhiều ứng viên phù hợp nhưng không chọn được một phương thức duy nhất.

Không cần xóa phương thức `max(String)` hay đổi quyền truy cập để sửa lời gọi số học; viết `Math.max(1, 2)` đã thể hiện đúng mục tiêu.

## 8. Cách chẩn đoán một lỗi static import

Khi gặp lỗi, kiểm tra theo thứ tự:

1. **Kiểu và thành viên:** tên kiểu đầy đủ có đúng không, thành viên có thật sự là static không?
2. **Quyền truy cập:** kiểu chứa thành viên và thành viên có truy cập được tại khai báo import không? Có đang nhầm package con với cùng package không?
3. **Phạm vi tên:** biến cục bộ, tham số, trường hoặc phương thức trong lớp có cùng tên và đang che nguồn import không?
4. **Nguồn cạnh tranh:** có nhiều trường hoặc nhiều phương thức từ các lớp khác nhau cùng tham gia không?
5. **Lời gọi cụ thể:** với phương thức, kiểu và số lượng đối số có làm xuất hiện một lựa chọn hợp lệ duy nhất không?
6. **Cách sửa thể hiện ý định:** dùng tên có chủ sở hữu khi nó giúp chỉ rõ nguồn thành viên.

Bảng định hướng:

| Dấu hiệu | Hướng tìm nguyên nhân |
|---|---|
| Lỗi ngay tại import tường minh | Tên sai, thành viên không static, kiểu hoặc thành viên không truy cập được |
| Không tìm thấy tên sau import dấu `*` | Thành viên có thể đã bị lọc bởi quyền truy cập, hoặc không thuộc nguồn được nhập |
| `reference ... is ambiguous` | Có nhiều ứng viên; xác định chúng rồi chỉ rõ nguồn |
| `method ... cannot be applied` dù đã import một phương thức phù hợp | Kiểm tra phương thức cùng tên trong lớp và tập phương thức thực sự đang được xét |
| Mã biên dịch nhưng lấy giá trị khác dự đoán | Kiểm tra biến/trường cùng tên đang che trường được import |

Không sửa bằng việc mở rộng `private` thành `public` chỉ để import thành công nếu thành viên vốn là chi tiết nội bộ. Trước hết xác định API nào thực sự nên được nơi gọi sử dụng.

## 9. Tự kiểm tra

### Tình huống 1

Một tệp có `import static demo.api.Symbols.LIMIT;`, nhưng trong phương thức có `int LIMIT = 5;`. `System.out.println(LIMIT)` in gì?

**Đáp án:** In 5. Muốn đọc trường đã nhập, dùng `demo.api.Symbols.LIMIT`.

### Tình huống 2

Đảo thứ tự hai import tường minh trong ví dụ `AmbiguousField` có hết lỗi không?

**Đáp án:** Không. Thứ tự dòng không chọn giữa hai trường. Cần loại bỏ nguồn cạnh tranh hoặc viết rõ chủ sở hữu.

### Tình huống 3

Một lớp `demo.Child` kế thừa `demo.api.Symbols`. Có thể suy ra rằng `import static demo.api.Symbols.PROTECTED_LIMIT;` ở đầu tệp sẽ hợp lệ không?

**Đáp án:** Không. Quyền truy cập trong thân lớp con và quyền tại khai báo import là hai ngữ cảnh khác nhau. Ví dụ `ProtectedDemo` dùng thành viên kế thừa trực tiếp trong thân lớp.

### Tình huống 4

Hai import tên phương thức `choose` ở ví dụ overload có lỗi ngay vì trùng tên không?

**Đáp án:** Không. Các lời gọi `choose(1)` và `choose(1L)` phân giải được; riêng `choose("A")` mơ hồ do cả hai lớp có phương thức nhận `String`.

Khi đọc một tên ngắn từ static import, hãy xác định lần lượt **quyền truy cập → phạm vi và che khuất → nguồn ứng viên → chữ ký lời gọi nếu là phương thức**. Tên có chủ sở hữu là công cụ hữu ích khi cần làm rõ kết quả phân giải.
