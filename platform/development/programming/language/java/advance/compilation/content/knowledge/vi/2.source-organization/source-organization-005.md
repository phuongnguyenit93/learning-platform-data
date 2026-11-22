# Tên nhị phân của lớp lồng nhau và các tệp `.class` được sinh

## 1. Vì sao cần hiểu tên nhị phân?

Một tệp nguồn Java có thể khai báo nhiều kiểu: lớp cấp cao nhất (*top-level class*), lớp thành viên (*member class*), lớp lồng nhau `static`, lớp cục bộ (*local class*) và lớp vô danh (*anonymous class*). Khi biên dịch, `javac` thường sinh **một tệp `.class` cho mỗi lớp hoặc kiểu cần biểu diễn**, chứ không mặc định chỉ một tệp cho mỗi `.java`. Tên tệp phụ thuộc vào **tên nhị phân** (*binary name*) của kiểu và tên gói.

Điều này quan trọng khi:
- Đọc thư mục build, nội dung JAR và kết quả `javap`; xác định một `.class` đến từ khai báo nào.
- Dùng reflection, `Class.forName(...)`, cấu hình nạp lớp hoặc xử lý `ClassNotFoundException`.
- Phân biệt tên dùng trong mã nguồn với tên JVM dùng để liên kết các lớp đã biên dịch.
- Đóng gói, triển khai và gỡ lỗi khi thiếu một trong các tệp `.class` được sinh.

Cần phân biệt **tên nhị phân** với **tên chính tắc** (*canonical name*), **tên đơn giản** (*simple name*) và **tên nội bộ JVM** (*internal name*). Dấu `$` trong tên nhị phân không có nghĩa mọi lớp mang dấu `$` đều chắc chắn là lớp lồng nhau: `$` cũng là ký tự hợp lệ trong định danh Java.

## 2. Quy tắc đặt tên

Giả sử có gói `demo` và lớp cấp cao nhất `Outer`:

| Kiểu khai báo | Viết/nhìn trong mã nguồn | Tên nhị phân điển hình | Tệp lớp trong `out/demo/` |
| --- | --- | --- | --- |
| Lớp cấp cao nhất | `Outer` | `demo.Outer` | `Outer.class` |
| Lớp thành viên không `static` | `Outer.Inner` | `demo.Outer$Inner` | `Outer$Inner.class` |
| Lớp thành viên `static` | `Outer.Nested` | `demo.Outer$Nested` | `Outer$Nested.class` |
| Lớp thành viên sâu hơn | `Outer.Middle.Leaf` | `demo.Outer$Middle$Leaf` | `Outer$Middle$Leaf.class` |
| Lớp cục bộ tên `Local` | `Local` trong một khối | ví dụ `demo.Outer$1Local` | ví dụ `Outer$1Local.class` |
| Lớp vô danh | `new Runnable() { ... }` | ví dụ `demo.Outer$1` | ví dụ `Outer$1.class` |

**Quy tắc cốt lõi:**
1. Kiểu cấp cao nhất có tên nhị phân là tên gói, dấu chấm, rồi tên kiểu: `demo.Outer`. Trong *default package* không có tiền tố gói.
2. Kiểu thành viên có tên nhị phân `<tên nhị phân của kiểu chứa>$<tên thành viên>`. Quy tắc này dùng cho cả lớp `static` lẫn lớp thành viên không `static`; chữ `static` **không** làm đổi dấu phân cách.
3. Lớp cục bộ có phần hậu tố chứa một hoặc nhiều chữ số trước tên đơn giản; lớp vô danh có phần hậu tố chữ số mà không có tên đơn giản. Ví dụ số `1` ở bảng là kết quả có thể gặp từ `javac`, **không phải số ổn định để lập trình dựa vào**. Thứ tự đánh số, vị trí và số tệp sinh ra có thể thay đổi theo mã nguồn hoặc trình biên dịch.
4. Dấu chấm trong `demo.Outer.Inner` là cách viết tên kiểu thành viên trong Java và cũng là tên chính tắc của nó. Tên nhị phân tương ứng dùng `$`: `demo.Outer$Inner`. Lớp cục bộ và lớp vô danh **không có tên chính tắc**.

Một gói Java có thể có nhiều lớp cấp cao nhất không `public` trong một tệp nguồn; mỗi lớp đó cũng có tên nhị phân và tệp `.class` riêng. Với `public class Outer`, tên tệp nguồn thông thường phải là `Outer.java`.

## 3. Thí nghiệm có thể chạy trên Java 17+

Tạo tệp `src/demo/Outer.java` với toàn bộ nội dung sau:

~~~java
package demo;

public class Outer {
    private final String label;

    public Outer(String label) {
        this.label = label;
    }

    public class Inner {
        public String text() { return label + "/Inner"; }
    }

    public static class Nested {
        public String text() { return "Nested"; }
    }

    public void run() {
        class Local {
            String text() { return "Local"; }
        }

        Runnable anonymous = new Runnable() {
            @Override public void run() {
                System.out.println("Anonymous");
            }
        };

        System.out.println(new Inner().text());
        System.out.println(new Nested().text());
        System.out.println(new Local().text());
        anonymous.run();

        System.out.println(Inner.class.getName());
        System.out.println(Inner.class.getCanonicalName());
        System.out.println(Nested.class.getName());
        System.out.println(Local.class.getName());
        System.out.println(Local.class.getCanonicalName());
        System.out.println(anonymous.getClass().getName());
        System.out.println(anonymous.getClass().getCanonicalName());
    }

    public static void main(String[] args) {
        new Outer("Outer").run();
    }
}
~~~

Ở thư mục dự án chứa `src`, tạo thư mục `out` (chẳng hạn bằng `mkdir out`) rồi chạy:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Outer.java
java -cp out demo.Outer
~~~

Đầu ra chuẩn của chương trình trên khi biên dịch bằng `javac`:

~~~text
Outer/Inner
Nested
Local
Anonymous
demo.Outer$Inner
demo.Outer.Inner
demo.Outer$Nested
demo.Outer$1Local
null
demo.Outer$1
null
~~~

Trong phép thử với `javac --release 17`, các tệp được tạo gồm:

~~~text
out/
└── demo/
    ├── Outer.class
    ├── Outer$Inner.class
    ├── Outer$Nested.class
    ├── Outer$1Local.class
    └── Outer$1.class
~~~

Thứ tự liệt kê tệp trên máy có thể khác. Hai tên chứa số là **ví dụ cụ thể từ chương trình và `javac` này**; nếu bổ sung lớp cục bộ, lớp vô danh hoặc thay compiler, đừng coi chỉ số là cam kết tương thích. Lệnh `-d out` yêu cầu `javac` xuất class theo cấu trúc gói vào thư mục `out`. Lệnh `java -cp out demo.Outer` chạy theo **tên nhị phân** của lớp có `main`, không dùng tên đường dẫn `out/demo/Outer.class`.

### Phân tích từng loại

**`Outer.class`.** Đây là lớp cấp cao nhất `demo.Outer`. Trong bytecode của `Outer` có các tham chiếu đến các lớp lồng nhau, nhưng bản thân lớp lồng nhau vẫn có tệp class độc lập.

**`Outer$Inner.class`.** Đây là lớp thành viên **không `static`**. Nó có thể truy cập trường đối tượng `label` của `Outer`. Cách khởi tạo từ ngoài một phương thức thể hiện rõ đối tượng bao quanh:

~~~java
Outer outer = new Outer("A");
Outer.Inner inner = outer.new Inner();
System.out.println(inner.text()); // A/Inner
~~~

Đoạn trên là ví dụ sử dụng trong một phương thức có thể chạy, **không phải tệp Java độc lập**. Trong ví dụ đầy đủ, `new Inner()` được gọi ngay bên trong phương thức instance của `Outer`, nên compiler dùng đối tượng `this` hiện tại làm đối tượng bao quanh. Constructor ở bytecode thường có thêm tham số đầu tiên là `Outer` để truyền tham chiếu này; vì vậy reflection tìm constructor chỉ với các tham số được viết trong source có thể thất bại.

**`Outer$Nested.class`.** Đây là lớp thành viên `static`. Có thể tạo bằng `new Outer.Nested()` mà không cần instance của `Outer`. Nó vẫn dùng `$` trong tên nhị phân. Khác biệt `static`/không `static` là về ngữ nghĩa đối tượng bao quanh và phạm vi truy cập, **không phải việc có hay không có dấu `$`**.

**`Outer$1Local.class`.** `Local` chỉ được khai báo và sử dụng trong `run()`. Nó có tên đơn giản `Local` nhưng không có tên chính tắc, nên `Local.class.getCanonicalName()` trả `null`. Nó có thể capture biến cục bộ hoặc tham số *final/effectively final* của khối chứa, theo quy tắc Java.

**`Outer$1.class`.** Đây là kiểu lớp vô danh tạo bởi `new Runnable() { ... }`. Lớp vẫn là một lớp thực trong bytecode, được gán một tên nhị phân để JVM nạp. Nó không có tên đơn giản hay chính tắc; `anonymous.getClass().getCanonicalName()` trả `null`. Không nhầm kiểu vô danh này với một biểu thức lambda: các phiên bản JVM hiện đại có thể triển khai lambda bằng lớp ẩn (*hidden class*) tại runtime và không nhất thiết tạo tệp `Outer$$Lambda$...class` trong thư mục build.

## 4. So sánh các API lấy tên lớp

Với `Outer.Inner.class` trong ví dụ:

| Biểu thức | Kết quả |
| --- | --- |
| `getName()` | `demo.Outer$Inner` |
| `getCanonicalName()` | `demo.Outer.Inner` |
| `getSimpleName()` | `Inner` |
| `getTypeName()` | `demo.Outer$Inner` |
| `getDeclaringClass().getName()` | `demo.Outer` |

Với `Local.class`, `getSimpleName()` là `Local`, `getCanonicalName()` là `null`, `getDeclaringClass()` là `null`, còn `getEnclosingMethod()` có thể chỉ ra phương thức `run`. Với lớp vô danh, `getSimpleName()` là chuỗi rỗng và `getCanonicalName()` là `null`. `getEnclosingClass()` giúp tìm lớp chứa về mặt từ vựng đối với kiểu cục bộ/vô danh; `getDeclaringClass()` chỉ dành cho kiểu **thành viên** được khai báo trực tiếp trong một lớp hoặc interface. Vì vậy hai API này không thay thế cho nhau.

**Lưu ý về `Class.forName`.** Với lớp thành viên, API nhận tên nhị phân:

~~~java
Class<?> type = Class.forName("demo.Outer$Inner");
System.out.println(type.getName()); // demo.Outer$Inner
~~~

Đây là đoạn dùng trong phương thức khai báo `throws ClassNotFoundException` (hoặc xử lý ngoại lệ), khi `demo.Outer$Inner` có trên classpath. Gọi `Class.forName("demo.Outer.Inner")` không tìm đúng lớp này: dấu chấm ở đó là dạng tên chính tắc dùng trong Java source. Một số thư viện hoặc công cụ cấu hình có cú pháp riêng; cần xem rõ nó mong đợi *binary name*, *canonical name* hay cách viết do công cụ định nghĩa.

**Trường hợp mảng.** `getName()` của lớp mảng không đơn giản là tên nhị phân kèm `[]`. Ví dụ `Outer.Inner[].class.getName()` là `[Ldemo.Outer$Inner;`, trong khi `getCanonicalName()` là `demo.Outer.Inner[]`. Ký hiệu `[L...;` là cách JVM thể hiện mảng tham chiếu trong tên `Class`.

## 5. Tên nhị phân, tên nội bộ JVM và descriptor

Trong mã nguồn, người viết dùng `demo.Outer.Inner`; trong `Class.getName()` của kiểu thành viên nhận `demo.Outer$Inner`. Trong *class file*, JVM cũng sử dụng **tên nội bộ**: đổi dấu chấm phân tách gói thành `/`, nhưng giữ dấu `$` của phần tên lớp.

| Dạng | Ví dụ và ngữ cảnh |
| --- | --- |
| Tên dùng trong source / canonical | `demo.Outer.Inner` |
| Binary name | `demo.Outer$Inner` |
| Internal name | `demo/Outer$Inner` |
| Field/type descriptor tham chiếu | `Ldemo/Outer$Inner;` |
| Descriptor mảng một chiều | `[Ldemo/Outer$Inner;` |
| Đường dẫn trong output/JAR | `demo/Outer$Inner.class` |

Ở cấp độ class file, `L...;` bao quanh tên nội bộ để tạo descriptor cho kiểu tham chiếu; `[` biểu thị một chiều mảng. Không thay dấu `$` bằng dấu `/` để biểu diễn quan hệ lồng nhau; dấu `/` trong tên nội bộ dùng để phân cách **gói**.

## 6. Điều gì được lưu trong bytecode?

Tên tệp `.class` giúp định vị kiểu, còn các thuộc tính bên trong class file bổ sung thông tin về quan hệ lồng nhau:

- **`InnerClasses`** mô tả các kiểu thành viên và các thông tin tương ứng về kiểu lồng nhau. Đừng kết luận kiểu `static` chỉ từ dấu `$` trong tên tệp; xem metadata của class.
- **`EnclosingMethod`** có thể ghi thông tin lớp/phương thức bao quanh cho lớp cục bộ hoặc lớp vô danh. Reflection dựa vào metadata phù hợp để trả lời các câu hỏi về phương thức hoặc constructor bao quanh.
- **`NestHost` / `NestMembers`** (nestmates, từ Java 11) cho phép các lớp thuộc cùng nest truy cập thành viên `private` theo quy tắc kiểm tra truy cập JVM. Chúng không biến nhiều `.class` thành một file duy nhất.
- **Thành viên tổng hợp (*synthetic*)** có thể được compiler sinh để giữ tham chiếu tới đối tượng bao quanh, capture dữ liệu hoặc phục vụ cơ chế biên dịch. Ví dụ field thường thấy là `this$0`, nhưng **tên và sự tồn tại của field không phải API ổn định**. Compiler có thể bỏ tham chiếu bao quanh nếu nó không cần thiết hoặc thay đổi cách triển khai theo phiên bản.

Có thể dùng lệnh sau để khám phá lớp thành viên sau khi đã chạy `javac` ở phần 3:

~~~text
javap -classpath out -private 'demo.Outer$Inner'
javap -classpath out -v 'demo.Outer$Inner'
~~~

Dấu nháy đơn giữ nguyên `$` trong Bash và PowerShell; với Windows `cmd.exe` dùng nháy kép quanh tên lớp. `-private` cho thấy thành viên không công khai, còn `-v` cho thấy cấu trúc class file, constant pool và các thuộc tính. Tùy bản `javac`/JDK, nội dung cụ thể của synthetic fields và các thuộc tính có thể khác; hãy dựa trên bytecode thực tế thay vì suy diễn từ tên tệp.

## 7. Hệ quả khi build, đóng gói và nạp lớp

**Compile và classpath.** `javac` viết output theo cấu trúc package dưới `-d`. JVM cần tìm đầy đủ các tệp lớp được tham chiếu trên classpath/module path. Chỉ sao chép `Outer.class` mà bỏ `Outer$Inner.class` có thể làm chương trình lỗi khi mã bắt đầu sử dụng `Inner` (chẳng hạn `NoClassDefFoundError`). Việc lỗi xuất hiện ở thời điểm nào phụ thuộc quá trình nạp, liên kết và thực thi; không nhất thiết nổ ngay lúc khởi động.

**JAR.** Khi đóng gói nguyên thư mục output, các entry tương ứng thường là `demo/Outer.class`, `demo/Outer$Inner.class`, `demo/Outer$Nested.class`, v.v. Có thể kiểm tra bằng `jar tf ten-file.jar`. Tránh cấu hình exclude theo tên không hiểu ý nghĩa dấu `$`, vì có thể bỏ mất lớp thành viên/cục bộ/vô danh.

**Reflection.** Khi nạp bằng tên từ database, plugin hoặc file cấu hình, phải biết nó yêu cầu binary name hay tên khác. Khi khởi tạo inner class không `static` bằng reflection, constructor có thể yêu cầu instance của lớp bao quanh. Không suy luận constructor bytecode chỉ từ số tham số thấy ở source.

**Đổi tên/refactor.** Đổi tên `Outer` hoặc `Inner` sẽ đổi binary name của kiểu thành viên và đường dẫn `.class`. Client đã biên dịch, dữ liệu serialization hoặc cấu hình lưu tên cũ có thể hỏng dù source mới biên dịch thành công. Đối với API public, tên nhị phân là một phần nhận dạng kiểu ở mức liên kết. Tên lớp cục bộ/vô danh, đặc biệt phần chỉ số, càng không thích hợp để lưu bền vững hoặc dùng làm giao diện tích hợp.

**Dùng `$` trong tên thật.** Một lớp cấp cao nhất có thể được đặt tên chứa `$` theo cú pháp định danh Java; vì vậy không thể dựa vào chuỗi `$Inner` để khẳng định đó là lớp thành viên. Hãy kết hợp thông tin khai báo hoặc metadata (`InnerClasses`, reflection) khi cần xác định chính xác.

## 8. Những nhầm lẫn thường gặp

1. **“Một tệp `.java` sinh đúng một `.class`.”** Sai: source có nhiều khai báo kiểu, lớp cục bộ hoặc vô danh có thể tạo nhiều file.
2. **“Chỉ nested `static` mới có dấu `$`.”** Sai: cả member `static` và non-`static` đều dùng quy tắc tên nhị phân với `$`.
3. **“`Outer.Inner` truyền trực tiếp vào `Class.forName` được.”** Sai trong ví dụ này: API yêu cầu `demo.Outer$Inner`.
4. **“`Outer$1Local` mãi là tên của lớp cục bộ.”** Sai: số thứ tự là chi tiết có thể thay đổi sau chỉnh sửa source hoặc khi dùng compiler khác.
5. **“`getCanonicalName()` luôn trả một chuỗi.”** Sai: với local/anonymous class trả `null`; cần chọn `getName()` khi cần nhận dạng binary name.
6. **“Chỉ cần triển khai `Outer.class`.”** Sai nếu chương trình cần thêm các class phát sinh. Đóng gói đầy đủ output từ build.
7. **“Mọi tên bắt đầu bằng `Outer$$Lambda` đều là file do `javac` xuất.”** Sai: lambda có cơ chế triển khai riêng ở runtime; không giả định có các tệp tương ứng trong output.

## 9. Tự kiểm tra kiến thức

- Với `package p; class A { static class B { class C {} } }`, tên nhị phân của `C` là **`p.A$B$C`**; tính `static` của `B` không đổi quy tắc ghép tên.
- `Outer.Inner.class.getName()` trong ví dụ trả **`demo.Outer$Inner`**; `getCanonicalName()` trả **`demo.Outer.Inner`**.
- Khi thêm một anonymous class mới vào `run()`, hãy biên dịch lại rồi liệt kê `out/demo/`. Tệp chứa số có thể thay đổi; lời giải đúng phải dựa trên kết quả biên dịch thực tế, không khóa cứng vào `$1`.
- Nếu một JAR chứa `Outer.class` nhưng thiếu `Outer$Nested.class`, nên kiểm tra bước đóng gói và các entry trong JAR trước khi nghi ngờ import ở source.

**Ghi nhớ:** Tên thành viên viết bằng dấu chấm trong source, dùng dấu `$` trong binary name, và xuất thành các tệp `.class` riêng theo package. Với local/anonymous class, đọc tên được compiler sinh để chẩn đoán, nhưng không dùng các chỉ số của chúng làm hợp đồng ổn định.
