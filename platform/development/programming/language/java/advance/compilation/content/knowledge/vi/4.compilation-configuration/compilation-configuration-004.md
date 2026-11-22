# Điều khiển thông tin debug bằng -g

Khi Java biên dịch mã nguồn thành `.class`, JVM cần bytecode để thực thi, còn người lập trình thường cần thêm dữ liệu để biết **dòng nguồn nào đang chạy**, **biến cục bộ đang có tên gì** hoặc **nên đặt breakpoint ở đâu**. Những dữ liệu phụ trợ này được gọi là **thông tin gỡ lỗi (debug information)**. Trình biên dịch `javac` có thể ghi chúng vào classfile, và tùy chọn **`-g`** quyết định loại thông tin debug được tạo.

`-g` thuộc **giai đoạn biên dịch**. Nó không tự kích hoạt chế độ debug trong JVM, không mở cổng kết nối debugger, không in thêm log và không tự sửa lỗi của chương trình. IDE hoặc debugger lúc chạy sử dụng các thông tin đã được tạo để liên hệ bytecode với mã nguồn.

Bài học này tập trung vào bốn câu hỏi: thông tin debug gồm những gì, dùng `-g` và `-g:none` khác nhau ra sao, cách kiểm chứng bằng `javap`, và chọn cấu hình nào khi phát triển hoặc phát hành.

## 1. Vì sao metadata debug có giá trị?

Giả sử một chương trình ném `ArithmeticException`. Bạn muốn đọc stack trace với tên tệp và số dòng. Khi dừng tại breakpoint, bạn muốn debugger hiển thị biến `total` trong vòng lặp. JVM có thể chạy bytecode mà không cần tên biến nguồn, nhưng việc gỡ lỗi ở cấp Java trở nên khó hơn nếu thông tin ấy bị lược bỏ.

~~~text
DebugInfoDemo.java (mã nguồn)
          |
          | javac với lựa chọn -g tương ứng
          v
DebugInfoDemo.class
    |-- bytecode và cấu trúc cần cho JVM
    |-- SourceFile: thông tin tệp nguồn (nếu tạo)
    |-- LineNumberTable: ánh xạ vị trí bytecode sang dòng nguồn
    |-- LocalVariableTable: tên và phạm vi biến cục bộ
          |
          +--> JVM thực thi chương trình
          +--> debugger/javap đọc metadata để phân tích
~~~

Ba nhóm chính:

| Nhóm trong `-g:...` | Thuộc tính classfile thường liên quan | Ý nghĩa |
| --- | --- | --- |
| `source` | `SourceFile` | Ghi tên tệp nguồn đã dùng để biên dịch, chẳng hạn `DebugInfoDemo.java` |
| `lines` | `LineNumberTable` | Liên hệ các vị trí bytecode của một phương thức với số dòng trong nguồn |
| `vars` | `LocalVariableTable` | Mô tả tên, kiểu, slot và khoảng sống của biến cục bộ |

Với generic, có thể còn có `LocalVariableTypeTable` để biểu diễn chữ ký kiểu tổng quát. Đây không phải một từ khóa `-g:` thứ tư.

Các bảng trên **là metadata tùy chọn**. Classfile còn nhiều thành phần khác phục vụ việc nạp, xác minh và thực thi; không phải cứ tắt metadata debug là xóa hết tên lớp, phương thức, field, hằng hoặc thông tin kiểm tra bytecode.

## 2. Cú pháp và mặc định của `javac`

Với `javac` trên JDK hiện đại, bạn có thể dùng:

| Lệnh | Dữ liệu debug yêu cầu ghi |
| --- | --- |
| `javac Demo.java` | Mặc định có thông tin **dòng** và **tệp nguồn**, không yêu cầu bảng tên biến cục bộ |
| `javac -g Demo.java` | Tất cả thông tin debug: `lines`, `vars` và `source` |
| `javac -g:none Demo.java` | Không sinh các nhóm thông tin debug tùy chọn này |
| `javac -g:lines Demo.java` | Chỉ dữ liệu dòng |
| `javac -g:source Demo.java` | Chỉ dữ liệu tên tệp nguồn |
| `javac -g:vars Demo.java` | Chỉ dữ liệu biến cục bộ |
| `javac -g:lines,source Demo.java` | Có dữ liệu dòng và nguồn, không yêu cầu tên biến |
| `javac -g:lines,vars,source Demo.java` | Chọn cả ba nhóm, giống mục đích của `-g` |

Sau dấu hai chấm, nhiều từ khóa được ngăn cách bằng dấu phẩy và **không thêm dấu cách**. `none` là lựa chọn riêng để tắt các nhóm debug: không ghép `none` với `lines` hoặc `vars`.

**Không truyền `-g` khác với truyền `-g:none`.** Mặc định thông thường của `javac` vẫn ghi `lines` và `source`. Điều này giải thích tại sao một chương trình được build theo mặc định có thể cung cấp số dòng trong stack trace, dù người viết chưa từng chỉ định `-g`.

`-g` cũng khác chế độ kết nối debugger lúc chạy, chẳng hạn JDWP. Một bên xác định metadata trong `.class`, bên kia xác định cách công cụ debug tương tác với JVM.

## 3. Thí nghiệm hoàn chỉnh trên Java 17+: cùng nguồn, bốn cách biên dịch

Tạo tệp **`DebugInfoDemo.java`**, lưu UTF-8:

~~~java
public final class DebugInfoDemo {
    private DebugInfoDemo() {
    }

    public static int sumUpTo(int limit) {
        int total = 0;
        for (int i = 1; i <= limit; i++) {
            total += i;
        }
        return total;
    }

    public static void main(String[] args) {
        int limit = 4;
        int sum = sumUpTo(limit);
        System.out.println("Tổng từ 1 đến " + limit + " = " + sum);
    }
}
~~~

Biến `total`, `limit`, `sum` và `i` là những tên hữu ích để quan sát trong bảng biến cục bộ. Chương trình cộng 1+2+3+4, không cần thư viện ngoài JDK. Để dễ so sánh, mỗi cấu hình lưu classfile ở một thư mục riêng.

Tại thư mục chứa mã nguồn, tạo sẵn bốn thư mục:

~~~sh
mkdir out-default
mkdir out-full
mkdir out-none
mkdir out-selected
~~~

Chạy lệnh tạo thư mục một lần; nếu thư mục đã có, bỏ qua bước đó. Thư mục sau tùy chọn `-d` của `javac` phải tồn tại. Biên dịch cùng một mã nguồn:

~~~sh
javac -encoding UTF-8 -d out-default DebugInfoDemo.java
javac -encoding UTF-8 -g -d out-full DebugInfoDemo.java
javac -encoding UTF-8 -g:none -d out-none DebugInfoDemo.java
javac -encoding UTF-8 -g:lines,source -d out-selected DebugInfoDemo.java
~~~

Chạy từng sản phẩm biên dịch:

~~~sh
java -cp out-default DebugInfoDemo
java -cp out-full DebugInfoDemo
java -cp out-none DebugInfoDemo
java -cp out-selected DebugInfoDemo
~~~

**Mỗi lệnh `java` in một dòng:**

~~~text
Tổng từ 1 đến 4 = 10
~~~

Cả bốn lớp đều thực hiện cùng thuật toán, vì mã nguồn không đổi. Thứ cần khảo sát ở đây là **metadata** trong từng `.class`. Việc kết quả giống nhau không chứng minh mọi chi tiết classfile hoặc hiệu năng ứng dụng đều giống nhau ở mọi môi trường.

### Dùng `javap` kiểm tra bằng chứng

`javap` là công cụ thuộc JDK để hiển thị thông tin từ classfile; nó không chạy phương thức `main`. `-l` giúp xem bảng dòng và biến, `-p` gồm cả phương thức `private`:

~~~sh
javap -l -p -classpath out-default DebugInfoDemo
javap -l -p -classpath out-full DebugInfoDemo
javap -l -p -classpath out-none DebugInfoDemo
javap -l -p -classpath out-selected DebugInfoDemo
~~~

Bảng kỳ vọng:

| Bản biên dịch | `LineNumberTable` | `LocalVariableTable` | `SourceFile` |
| --- | --- | --- | --- |
| Mặc định | Có | Thông thường không | Có |
| `-g` | Có | Có | Có |
| `-g:none` | Không | Không | Không |
| `-g:lines,source` | Có | Không | Có |

Để thấy rõ `SourceFile` cùng thuộc tính khác, dùng chế độ verbose `-v`:

~~~sh
javap -v -p -classpath out-default DebugInfoDemo
javap -v -p -classpath out-full DebugInfoDemo
javap -v -p -classpath out-none DebugInfoDemo
javap -v -p -classpath out-selected DebugInfoDemo
~~~

Tìm **tên thuộc tính** `SourceFile`, `LineNumberTable`, `LocalVariableTable` trong đầu ra. Trong bản có `-g` đầy đủ, bạn có thể thấy các tên `limit`, `total` hoặc `sum` trong bảng biến. Việc chỉ tìm thấy chuỗi `sum` đâu đó trong constant pool **chưa đủ** để kết luận có `LocalVariableTable`.

Nếu muốn xem chỉ dẫn JVM, dùng:

~~~sh
javap -c -p -classpath out-full DebugInfoDemo
javap -c -p -classpath out-none DebugInfoDemo
~~~

`-c` hiển thị mã lệnh JVM. `-g` không biến bytecode thành nguồn Java và không tự thay đổi phép cộng. Với cùng công cụ và nguồn trong thí nghiệm, các lệnh thực hiện phép tính được kỳ vọng tương ứng; metadata debug là khác biệt chủ đích.

## 4. Đọc đúng từng loại thông tin

### `source`: tên nguồn, không phải nội dung nguồn

`SourceFile` thường cho biết tên tệp Java ban đầu. Ví dụ, `DebugInfoDemo.class` có thể ghi `DebugInfoDemo.java`. Metadata này **không chứa toàn văn mã nguồn** và không bảo đảm debugger có thể tìm thấy tệp nguồn đang lưu ở đâu. IDE cần tệp nguồn thật hoặc source attachment phù hợp và đúng phiên bản.

Nếu chỉ tạo `source` mà không có `lines`, debugger có thể biết tên tệp nhưng vẫn thiếu ánh xạ đến số dòng khi chương trình thực thi. Vì vậy hai nhóm thường được dùng cùng nhau.

### `lines`: vị trí bytecode và số dòng

`LineNumberTable` ánh xạ các vị trí trong bytecode của phương thức tới số dòng nguồn. Stack trace có thể tận dụng để hiển thị vị trí giống:

~~~text
at demo.Example.fail(Example.java:17)
~~~

Đây là ví dụ minh họa, **không phải đầu ra của `DebugInfoDemo`**. Số dòng thực tế thay đổi theo nội dung tệp. Nếu không có thông tin dòng, stack trace có thể bỏ số dòng hoặc hiển thị `Unknown Source`.

Không nên nghĩ một dòng Java tương ứng chính xác một chỉ dẫn JVM. Một dòng Java có thể được dịch thành nhiều chỉ dẫn; metadata ánh xạ chỉ phục vụ việc định vị.

### `vars`: tên, kiểu, slot và phạm vi

`LocalVariableTable` giúp công cụ thấy tên/phạm vi biến cục bộ như `total` và `i`. Trong `sumUpTo`, biến `i` nằm trong vòng lặp, còn `total` tồn tại qua các lần cộng. Mỗi mục có khoảng mã mà biến đó còn hợp lệ.

Bật `-g:vars` không bảo đảm debugger thấy **mọi biến tại mọi breakpoint**. Biến có thể chưa vào phạm vi, đã hết phạm vi, chưa có giá trị hoặc khó quan sát vì cách runtime tối ưu. Một field của lớp không giống một local variable; tên field cần được classfile giữ để các cơ chế liên kết/truy cập hoạt động, không tự biến mất với `-g:none`.

## 5. Minh họa stack trace có và không có số dòng

Tạo file **`FailureLocationDemo.java`**:

~~~java
public class FailureLocationDemo {
    static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }

    public static void main(String[] args) {
        try {
            divide(12, 0);
        } catch (ArithmeticException ex) {
            StackTraceElement frame = ex.getStackTrace()[0];
            System.out.println("Phương thức: " + frame.getMethodName());
            System.out.println("Có số dòng: " + (frame.getLineNumber() > 0));
        }
    }
}
~~~

Mã cố ý chia số nguyên cho 0 rồi bắt ngoại lệ để khảo sát frame ở vị trí lỗi. Lệnh mặc định:

~~~sh
javac -encoding UTF-8 FailureLocationDemo.java
java FailureLocationDemo
~~~

Kết quả thông thường:

~~~text
Phương thức: divide
Có số dòng: true
~~~

Biên dịch **lại** với `-g:none` và chạy cùng lớp:

~~~sh
javac -encoding UTF-8 -g:none FailureLocationDemo.java
java FailureLocationDemo
~~~

Kết quả:

~~~text
Phương thức: divide
Có số dòng: false
~~~

`getLineNumber()` không có số dòng dương nếu classfile thiếu thông tin dòng. Phương thức vẫn được gọi và ngoại lệ vẫn tồn tại; chỉ mất thông tin vị trí nguồn dùng để chẩn đoán. Ví dụ tránh cố định số dòng cụ thể vì người học có thể thêm/bớt dòng trong mã.

Nếu bạn dùng IDE hoặc build tool, cần đảm bảo `java` chạy đúng class vừa biên dịch, không phải lớp cũ trên classpath. Một bản classfile cũ có thể làm thí nghiệm cho kết quả không như mong đợi.

## 6. Phân biệt `-g:vars` và `-parameters`

Nhiều người tưởng `-g` sẽ khiến Reflection biết tên thật của tham số. Hai loại metadata khác nhau:

- `-g:vars` sinh thông tin **biến cục bộ** trong `LocalVariableTable` để hỗ trợ debugger. Tham số có thể xuất hiện dưới dạng biến của phương thức.
- `-parameters` sinh **MethodParameters** để API Reflection nhận biết tên tham số khai báo qua `Parameter.getName()` và `isNamePresent()`.

Tạo file **`ParameterNameDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNameDemo {
    public static void greet(String person) {
    }

    public static void main(String[] args) throws Exception {
        Method method =
                ParameterNameDemo.class.getDeclaredMethod("greet", String.class);
        Parameter parameter = method.getParameters()[0];

        System.out.println("Có tên thật: " + parameter.isNamePresent());
        System.out.println("Tên tham số: " + parameter.getName());
    }
}
~~~

Chỉ dùng `-g`:

~~~sh
javac -encoding UTF-8 -g ParameterNameDemo.java
java ParameterNameDemo
~~~

Stdout:

~~~text
Có tên thật: false
Tên tham số: arg0
~~~

Thêm `-parameters` và **biên dịch lại**:

~~~sh
javac -encoding UTF-8 -g -parameters ParameterNameDemo.java
java ParameterNameDemo
~~~

Stdout:

~~~text
Có tên thật: true
Tên tham số: person
~~~

Có thể dùng `javap -v -p ParameterNameDemo` để nhìn thấy `MethodParameters` ở bản thứ hai. Metadata biến cục bộ dùng cho debug và metadata tên tham số dùng cho reflection **không thay thế nhau**. Đây là điểm đáng chú ý khi framework dùng reflection để ánh xạ tham số API hoặc cấu hình.

## 7. Chọn `-g` trong phát triển và phát hành

| Mục tiêu | Cấu hình có thể chọn | Đánh đổi |
| --- | --- | --- |
| Build thông thường, giữ stack trace hữu ích | Mặc định | Không có đầy đủ tên biến cục bộ |
| Gỡ lỗi sâu tại IDE | `-g` hoặc `-g:lines,vars,source` | Có thêm metadata, có thể tăng dung lượng classfile |
| Giữ vị trí nguồn nhưng giảm thông tin biến | `-g:lines,source` | Debugger khó hiển thị tên biến cục bộ hơn |
| Muốn lược bỏ các bảng debug tùy chọn | `-g:none` | Stack trace mất số dòng, việc điều tra lỗi khó hơn |

**Không xem `-g:none` là biện pháp bảo mật hoặc chống dịch ngược đầy đủ.** Classfile vẫn còn bytecode, chữ ký, hằng số và các tên cấu trúc cần cho JVM. Giảm thông tin debug có thể làm file nhỏ hơn, nhưng không có nghĩa thuật toán nhanh hơn hoặc bí mật triển khai được giữ kín.

Trong production, số dòng thường rất hữu ích để xác định lỗi từ log/stack trace. Quyết định bỏ `lines` phải dựa trên khả năng quan sát hệ thống, quy mô vận hành và yêu cầu phân phối artifact.

### Ví dụ cấu hình Gradle

Một dự án dùng plugin Java và Gradle Groovy DSL có thể cấu hình tác vụ biên dịch:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.debug = true
    options.debugOptions.debugLevel = 'lines,vars,source'
}
~~~

Đây là **cấu hình Gradle**, không phải mã Java chạy độc lập. Nó chỉ có ý nghĩa khi được áp dụng trong build có nhiệm vụ `JavaCompile`. Các plugin và profile khác có thể thay đổi cấu hình, nên nên kiểm tra kết quả thực bằng `javap`.

Với Maven hoặc IDE cũng có lựa chọn tương đương, nhưng vị trí/cú pháp cấu hình phụ thuộc plugin và phiên bản. Đừng giả định IDE luôn dùng cùng compiler command như Gradle/Maven CLI; trong nhiều dự án IDE giao việc build cho công cụ bên ngoài.

## 8. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| “Không viết `-g` nghĩa là không có debug info.” | Mặc định `javac` thường sinh `lines` và `source`. |
| “`-g` kích hoạt debug ở JVM.” | `-g` tạo metadata khi biên dịch; debug tương tác là bước riêng. |
| “`-g:none` xóa mọi tên khỏi `.class`.” | Nó chỉ điều khiển debug metadata tùy chọn, không xóa cấu trúc lớp cần thiết. |
| “Có `SourceFile` thì công cụ có toàn bộ nguồn.” | `SourceFile` thường ghi tên tệp nguồn, còn file `.java` phải tìm riêng. |
| “`-g:vars` làm Reflection biết tên tham số.” | `-parameters` mới ghi metadata tên tham số cho Reflection. |
| “Mất dòng trên stack trace nghĩa là không chạy được.” | Chương trình vẫn chạy; chỉ thiếu metadata xác định dòng. |
| “Classfile nhỏ hơn là bytecode nhanh hơn.” | Chênh lệch có thể chỉ do bảng debug, không nói lên tốc độ. |
| “Có metadata thì mọi biến đều đọc được.” | Phạm vi sống, thời điểm dừng và tối ưu JVM vẫn quan trọng. |

Nếu IDE không cho thấy tên biến hoặc breakpoint không khớp dòng, nên kiểm tra:

1. **Artifact đang chạy:** Xác nhận đúng `.class` hoặc JAR vừa build, đúng classpath, không chạy phiên bản cũ.
2. **Metadata trong class:** Dùng `javap -l -p` xem `LineNumberTable` và `LocalVariableTable`; dùng `javap -v -p` khi cần thuộc tính chi tiết.
3. **Mã nguồn đúng phiên bản:** Một tệp nguồn sửa sau khi build không chắc khớp metadata trong class.
4. **Phạm vi của biến:** Một biến trong vòng lặp không cần tồn tại trước hoặc sau vòng lặp.
5. **Debugger đúng tiến trình/luồng:** Việc có metadata không bảo đảm JVM đã đi qua vị trí breakpoint.
6. **Compiler config thực tế:** Build tool/IDE có thể ghi đè lựa chọn `-g` khác điều bạn tưởng.
7. **Tối ưu runtime:** JIT và cách debugger hiển thị có thể khiến một số giá trị khó quan sát dù đã sinh metadata.

## 9. Thực hành và câu hỏi tự đánh giá

**Bài 1 — Đối chiếu classfile.** Biên dịch `DebugInfoDemo.java` với mặc định, `-g`, `-g:none` và `-g:lines,source`. Dùng `javap -v` ghi lại sự hiện diện của ba thuộc tính `SourceFile`, `LineNumberTable` và `LocalVariableTable`. Sau đó chạy cả bốn bản để xác nhận kết quả tính tổng.

**Bài 2 — Gỡ lỗi theo dòng.** Dùng `FailureLocationDemo.java` với mặc định và `-g:none`. So sánh boolean `getLineNumber() > 0`. Giải thích tại sao phép chia vẫn gây lỗi nhưng thông tin dòng thay đổi.

**Bài 3 — Xem biến cục bộ.** Biên dịch với `-g`, dùng `javap -l -p` và tìm `total`, `i` ở phương thức `sumUpTo`. Đọc các cột phạm vi, slot, kiểu và giải thích tại sao debugger cần chúng.

**Bài 4 — Reflection.** Chạy `ParameterNameDemo.java` theo hai cách và giải thích ý nghĩa `isNamePresent()`. Tìm `MethodParameters` bằng `javap -v` sau khi có `-parameters`.

**Bài 5 — Quyết định build.** Một ứng dụng production cần stack trace đầy đủ tệp và dòng nhưng muốn hạn chế metadata về tên biến cục bộ. Hãy lựa chọn `-g:lines,source` rồi giải thích điểm bất lợi của `-g:none`.

Tự trả lời sáu câu hỏi:

1. **`-g` tác động tới giai đoạn nào?** — Giai đoạn biên dịch bằng `javac`.
2. **Không truyền `-g` có đồng nghĩa `-g:none`?** — Không; mặc định thường vẫn có thông tin dòng và nguồn.
3. **Thông tin biến cục bộ nằm trong thuộc tính nào?** — `LocalVariableTable`, đôi khi thêm `LocalVariableTypeTable` cho chữ ký generic.
4. **Lệnh nào kiểm tra thuộc tính?** — `javap -l` cho bảng dòng/biến, `javap -v` cho chi tiết classfile.
5. **`-parameters` khác `-g:vars` ở đâu?** — Nó phục vụ Reflection đọc tên tham số khai báo, không chỉ debugger.
6. **`-g:none` có làm mất khả năng thực thi bytecode không?** — Không; nó bỏ debug metadata tùy chọn.

**Kết nối kiến thức:** Cấu hình biên dịch có thể ảnh hưởng lớn đến khả năng chẩn đoán khi chương trình chạy. Hiểu `-g` giúp bạn kiểm tra đúng mối quan hệ **mã nguồn → classfile → debugger/stack trace**, tránh nhầm vấn đề thiếu metadata với lỗi của JVM hoặc mã Java.