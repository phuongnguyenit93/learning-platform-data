# Tìm lỗi gốc khi một lỗi tạo ra nhiều thông báo dây chuyền trong javac

## 1. Một lỗi gốc có thể xuất hiện thành nhiều compiler errors

Khi biên dịch Java, trình biên dịch không nhất thiết dừng ở lỗi đầu tiên. Nó cố tiếp tục phân tích những phần còn lại để đưa ra nhiều chẩn đoán. Nếu một khai báo kiểu không tồn tại, mọi chỗ cần kiểu đó đều có thể gây thông báo khác: import, khai báo biến, lời gọi constructor, lời gọi method. Sửa từng dòng bị đánh dấu không giải quyết được nguồn gốc chung.

**Lỗi gốc (root cause)** là điều kiện sai nằm phía trước về mặt phụ thuộc, chẳng hạn JAR bị thiếu, một dấu ngoặc chưa đóng, một API signature thay đổi, hoặc generator chưa tạo class. **Lỗi dây chuyền (cascading errors)** là các lỗi phát sinh trong quá trình compiler cố phân tích mã phụ thuộc vào điều kiện sai đó.

~~~text
Một class Greeter không được tìm thấy
     |
     +-- import demo.lib.Greeter không phân giải
     +-- kiểu của biến Greeter không phân giải
     +-- new Greeter() không phân giải constructor
     +-- greeter.greet(...) thiếu thông tin về receiver
~~~

Sơ đồ thể hiện quan hệ nguyên nhân; nó không khẳng định javac luôn in đủ bốn thông báo hoặc in theo đúng thứ tự. Thông báo phụ thuộc phiên bản JDK, các flags, những file thực sự được biên dịch và khả năng compiler phục hồi sau lỗi.

Ba câu hỏi quan trọng hơn việc đếm dòng đỏ là: **các lỗi có phụ thuộc một khai báo hay nguồn dữ liệu chung không; có thể kiểm tra giả thuyết bằng một sửa đổi nhỏ không; và những lỗi nào còn tồn tại sau khi biên dịch lại?**

## 2. Compiler đang làm gì khi tiếp tục báo lỗi?

Có thể hiểu việc biên dịch bằng các công việc liên quan:

1. **Nhận đầu vào:** chọn source files, source roots, compile classpath, module path, release, processor và output.
2. **Phân tích cú pháp:** đọc tokens và cấu trúc class, method, expression. Một dấu ngoặc/nháy thiếu có thể khiến mã tiếp theo bị hiểu sai.
3. **Phân giải khai báo:** liên kết import và tên đơn với type, method, field tương ứng.
4. **Kiểm tra ngữ nghĩa:** xác minh quyền truy cập, generic bounds, assignment conversion, overload, static/instance context.
5. **Sinh nguồn hoặc xử lý annotation:** các processor có thể tạo types mà source khác tham chiếu.
6. **Tạo class files:** compiler chỉ tạo output phù hợp khi có đủ thông tin và không bị lỗi cản trở.

Đây là bản đồ khái niệm, không phải mô tả cứng thứ tự từng pass nội bộ của mọi javac. Một số bước có thể đan xen, annotation processing có nhiều vòng, và compiler có thể dùng *error type* để tiếp tục kiểm tra thay vì dừng lập tức.

Do đó, **thông báo xuất hiện đầu tiên trong terminal chưa chắc là lỗi gốc**. Lỗi upstream có thể thuộc file khác, task khác hoặc đã bị log CI cắt bớt. Cần lần theo quan hệ dependency giữa các khai báo.

## 3. Ví dụ Java 17+ chạy được: thiếu một nguồn tạo nhiều lỗi

Tạo hai tệp trong project có cấu trúc:

~~~text
project/
├── src/
│   ├── library/demo/lib/Greeter.java
│   └── app/demo/app/Main.java
└── out/
    ├── library/
    └── app/
~~~

Tệp **src/library/demo/lib/Greeter.java**:

~~~java
package demo.lib;

import java.util.Locale;

public final class Greeter {
    public String greet(String name) {
        return "HELLO, " + name.toUpperCase(Locale.ROOT);
    }
}
~~~

Tệp **src/app/demo/app/Main.java**:

~~~java
package demo.app;

import demo.lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        String message = greeter.greet("Java");
        System.out.println(message);
    }
}
~~~

Chương trình hợp lệ. Nhưng nếu đứng tại thư mục **project** và chỉ biên dịch file Main:

~~~bash
mkdir -p out/app
javac --release 17 -encoding UTF-8 -d out/app src/app/demo/app/Main.java
~~~

lệnh không cung cấp `Greeter.java` và cũng không cung cấp class đã biên dịch của Greeter. Trong tình huống từ output/source path sạch như ví dụ, compiler không resolve được `demo.lib.Greeter`. Những thông báo có thể mang dạng:

~~~text
package demo.lib does not exist
cannot find symbol
  symbol: class Greeter
~~~

Đây chỉ là **các dạng thông báo** có thể gặp, không phải stdout/stderr đầy đủ hoặc số lỗi được cam kết. Nhiều vị trí khác nhau trong Main cùng phụ thuộc `Greeter`, nên một lỗi thiết lập build tạo cả nhóm diagnostics.

### 3.1. Sửa nguyên nhân: cung cấp đủ source trong cùng lần compile

~~~bash
javac --release 17 -encoding UTF-8 -d out/app src/library/demo/lib/Greeter.java src/app/demo/app/Main.java
java -cp out/app demo.app.Main
~~~

Stdout chính xác:

~~~text
HELLO, JAVA
~~~

### 3.2. Hoặc biên dịch thư viện rồi dùng classpath của ứng dụng

~~~bash
mkdir -p out/library out/app
javac --release 17 -encoding UTF-8 -d out/library src/library/demo/lib/Greeter.java
javac --release 17 -encoding UTF-8 -cp out/library -d out/app src/app/demo/app/Main.java
java -cp 'out/library:out/app' demo.app.Main
~~~

Trên Windows/PowerShell, dùng dấu chấm phẩy cho runtime classpath:

~~~powershell
java -cp 'out/library;out/app' demo.app.Main
~~~

Stdout vẫn là:

~~~text
HELLO, JAVA
~~~

Không cần sửa một dòng source nào: chỉ cần đưa dependency đúng vào compile classpath hoặc danh sách đầu vào. Đó là bằng chứng thực nghiệm rằng nhóm diagnostics cùng xuất phát từ nguồn thiếu.

Nếu một dependency có thực nhưng vẫn không tìm thấy type, kiểm tra tên package, fully qualified name, source root, compile classpath và class file/JAR thực tế; **import không tự tải một thư viện**.

## 4. Lỗi cú pháp gốc khiến parser hiểu sai nhiều dòng sau

Một dấu `}` bị thiếu có thể làm compiler tiếp tục hiểu những khai báo sau như nội dung của method trước. Ví dụ cố ý sai, không phải file chạy được:

~~~java
class Broken {
    static int add(int a, int b) {
        return a + b;
    // Thiếu dấu } đóng add ở đây.

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

Compiler có thể báo lỗi tại khai báo main, tại những token sau đó và tại cuối file, dù các dòng ấy nhìn riêng có vẻ hợp lệ. Cách tìm lỗi gốc:

- Kiểm tra dấu ngoặc mở/đóng, dấu nháy, dấu kết thúc biểu thức từ **trước dòng đầu tiên được đánh dấu**.
- Sửa dấu `}` bị thiếu sau `return a + b;`.
- Biên dịch lại thay vì sửa mọi dòng đang bị gạch đỏ.
- Nếu vẫn còn lỗi, phân tích diagnostics mới trên bản source đã hợp lệ.

Tệp đúng độc lập **ParseFixed.java**:

~~~java
public class ParseFixed {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac --release 17 ParseFixed.java
java ParseFixed
~~~

Stdout:

~~~text
5
~~~

**Lưu ý:** thứ tự dòng compiler báo lỗi không đồng nghĩa đúng vị trí token gây lỗi. Một dấu nháy chưa đóng hoặc cấu trúc lambda/block thiếu dấu ngoặc có thể làm cả đoạn dài trông như sai. Sau khi parser lấy lại cấu trúc đúng, nhiều thông báo tự biến mất.

## 5. API signature sai có thể làm hàng loạt caller lỗi

Giả sử thư viện từng khai báo `int parse(String text)`, sau đó đổi thành `int parse(String text, int radix)`. Những caller vẫn dùng `parse("12")`, `parse("7")` và `parse("101")` có thể đồng loạt bị lỗi về số lượng đối số.

~~~java
// Chỉ là minh họa signature, không phải chương trình độc lập.
static int parse(String text, int radix) {
    return Integer.parseInt(text, radix);
}

// Các lời gọi cũ không còn khớp signature:
parse("12");
parse("7");
~~~

Nếu API đổi có chủ đích, sửa caller theo contract mới; nếu thay đổi declaration là nhầm lẫn, sửa API tại nguồn. Không phải cứ nhiều `method cannot be applied` là mọi caller đều sai độc lập.

Tương tự:

- Một generic bound mới như `<T extends Number>` có thể khiến hàng loạt lời gọi truyền `String` bị từ chối.
- Một method đổi return type từ `T` thành `Optional<T>` có thể làm nhiều assignment và chained calls lỗi.
- Một overload được thêm có thể gây ambiguity tại một số call sites.

Ví dụ độc lập về overload ambiguity trong **OverloadFixed.java**:

~~~java
public class OverloadFixed {
    static void accept(String value) {
        System.out.println("string");
    }

    static void accept(Integer value) {
        System.out.println("integer");
    }

    public static void main(String[] args) {
        accept((String) null);
    }
}
~~~

~~~bash
javac --release 17 OverloadFixed.java
java OverloadFixed
~~~

Stdout:

~~~text
string
~~~

Nếu thay lời gọi thành `accept(null)`, compiler không chọn duy nhất được `accept(String)` hoặc `accept(Integer)` vì hai kiểu không có quan hệ subtype phân định overload. Root cause nằm ở lời gọi mơ hồ; cast hợp lệ khi ta thực sự muốn chọn overload String.

Không áp dụng máy móc “sửa API cho tất cả”: khi caller vi phạm một API đúng, root cause chính là caller. Hãy so sánh expected types, actual types, lịch sử thay đổi hợp đồng và yêu cầu nghiệp vụ.

## 6. Annotation processor và generator: lỗi ở producer

Một số class không do người viết tạo ra mà được sinh từ schema, annotation hoặc cấu hình. Một generator thất bại có thể làm nhiều consumer không tìm được cùng generated type.

~~~text
schema / annotated sources
           |
       generator task
           |
    GeneratedMapper.java
           |
      compile consumer
       /    |     \
      A     B      C
      nhiều lỗi không tìm thấy cùng một type
~~~

Các bước xác minh cần thiết:

1. Generator/annotation processor đã **thực sự chạy** trước consumer chưa?
2. Nếu là annotation processor, processor có ở processor path/`annotationProcessor` phù hợp không?
3. Generated source root thuộc đúng source set `main` hay `test` chưa?
4. Task producer có khai báo output và phụ thuộc của compiler task đúng không?
5. Có thông báo lỗi **ở generator** xuất hiện trước những lỗi không tìm thấy class không?
6. Từ clean build, generated source có được tái tạo không?

Không nên tạo class giả hoặc copy thủ công output vào `src/main/java` để che giấu lỗi producer. Thay vào đó, sửa generator, input/schema và task dependency. Với annotation processing nhiều vòng, hãy đọc diagnostic của processor và kiểm tra tên/kiểu source sinh được, tránh chỉ nhìn lỗi consumer.

## 7. Root cause ở build configuration, không nằm trong mã bị gạch đỏ

Một vài kiểu nguyên nhân xuất hiện rất thường xuyên:

| Nhóm diagnostic | Nguồn gốc cần điều tra |
| --- | --- |
| `package ... does not exist` rồi nhiều `cannot find symbol` | JAR/source root thiếu, sai package hoặc dependency scope |
| `module not found`, package không visible | JPMS module path, `requires`, `exports` |
| Nhiều class được sinh không tìm thấy | Generator/task/annotation processor chưa chạy hoặc output sai |
| Nhiều lỗi sau đổi JDK | `--release`, toolchain, API/platform version, dependency minimum Java |
| Nhiều lỗi trong test nhưng main compile tốt | Test source set, test compile classpath hoặc test-only dependencies |
| Một class có hai định nghĩa hoặc kiểu API khác kỳ vọng | Duplicate class hoặc JAR version conflict |
| Chạy trên IDE tốt, CI compile lỗi | Classpath/toolchain/processor của IDE khác build, output cũ |
| Warnings dẫn đến build thất bại | Tùy chọn `-Werror` hoặc chính sách compiler plugin |

Lỗi xảy ra trong **test compile** không nhất thiết phải sửa code main. Lỗi trong module downstream có thể do một module upstream không build được; đọc task đầu tiên thất bại, dependency graph và log bắt đầu từ phần upstream.

Trong Java Platform Module System, hai vấn đề thường bị nhầm:

- **Readability:** client module có `requires provider.module` hoặc một cơ chế read edge hợp lệ chưa?
- **Exports:** package chứa public API có được provider module export cho client không?

Một class `public` vẫn có thể không accessible nếu package không exported. Sửa bằng cấu hình module và public API contract đúng, không phải cứ thêm wildcard classpath là giải quyết.

## 8. Cách đọc diagnostics của javac

Một diagnostic có thể chứa tên file, dòng, cột/caret, nội dung lỗi, và các dòng ngữ cảnh như `symbol:` / `location:`. Giữ đầy đủ các chi tiết này khi điều tra.

Khi log dài:

- Ghi lại chính xác lệnh `javac`, phiên bản từ `javac -version`, source files, classpath/module path, release và annotation processor.
- Kiểm tra log có bị cắt không. Một số phiên bản compiler hạn chế số lỗi hiển thị; hạ tầng CI cũng có thể giới hạn output.
- Nhóm theo **cùng symbol/package/file phụ thuộc**, chứ không chỉ đếm tổng số errors.
- Với overload/generics, dùng chế độ diagnostics chi tiết được compiler hỗ trợ để đọc expected/actual types và các candidate methods; kiểm tra `javac --help-extra` / tài liệu của JDK đang dùng.
- Phân biệt **warning** và **error**. Khi chính sách biến warning thành build failure, tìm warning gốc thay vì chỉ nhìn thông báo tổng kết.

Không cố so sánh nguyên văn toàn bộ stderr giữa hai JDK khác phiên bản. Compiler có thể thay đổi cách sắp và trình bày diagnostics mà nguyên nhân lập trình vẫn như nhau.

### Vì sao tăng số lỗi hiển thị không đồng nghĩa dễ tìm root hơn?

Một log có 100 diagnostics chưa chắc cho thêm thông tin hữu ích so với 20 diagnostics nếu tất cả cùng bắt nguồn từ một type không phân giải. Tăng giới hạn chẩn đoán có thể hữu ích khi nhiều nguyên nhân gốc độc lập bị che khuất, nhưng không thay thế thao tác nhóm lỗi.

Ngược lại, **chỉ xem dòng lỗi đầu tiên** cũng có thể sai nếu log sắp theo thứ tự xử lý file hoặc lỗi root nằm tại task sinh mã trước đó. Phải giữ đủ ngữ cảnh và kiểm tra quan hệ phụ thuộc giữa các thành phần.

## 9. Quy trình điều tra có thể lặp lại

**Bước 1: Xác định pha thất bại.** Có phải `javac` compile main, compile test, generator, dependency resolution hay module build? Nếu build tool không chạy được javac thì trước hết xử lý cấu hình/task.

**Bước 2: Cố định môi trường.** Ghi JDK/compiler, Gradle/Maven task, source set/module và revision. Nếu build sạch khác build incremental, tìm stale classes hoặc generator outputs.

**Bước 3: Lấy log đủ.** Không chỉ lấy dòng `N errors`; đọc các đoạn có file/line, symbol/location và thông báo của task upstream.

**Bước 4: Nhóm lỗi.** Những lỗi nào cùng nhắc tới một class, package, method hoặc generated source? Những lỗi nào xuất hiện sau một parser error hoặc API signature đổi?

**Bước 5: Đề xuất một giả thuyết gốc có kiểm chứng.** Ví dụ “compiler chưa thấy `demo.lib.Greeter` vì main compile chưa có thư viện ở compile classpath”. Kiểm tra nguồn, JAR và lệnh compile để xác minh.

**Bước 6: Sửa một nguyên nhân đã xác nhận.** Bổ sung đúng dependency, sửa package/source root, cân bằng dấu ngoặc, sửa declaration hoặc nối task generator vào compiler.

**Bước 7: Biên dịch lại từ điều kiện tương đương.** So sánh **nhóm** lỗi đã mất, nhóm còn lại và lỗi mới lộ diện. Nếu còn lỗi độc lập, lặp lại từ bước 4.

**Bước 8: Chạy test/runtime tương ứng.** Compile thành công vẫn có thể bỏ sót binary compatibility hoặc runtime dependency issues.

Cách ghi chép ngắn gọn:

~~~text
Điều kiện: javac/JDK, source set, module, command
Giả thuyết: khai báo hoặc nguồn phụ thuộc nào là gốc?
Bằng chứng: diagnostics và kiểm tra classpath/source
Sửa đổi: một thay đổi có lý do
Kết quả: nhóm errors nào biến mất, nhóm nào còn
Xác minh: compile sạch, test, chạy phù hợp
~~~

Đây là cách làm đặc biệt hiệu quả với nhiều file hoặc một lỗi có hàng trăm vị trí bị ảnh hưởng.

## 10. Gradle, Maven và IDE: đọc đúng nơi báo lỗi

**Gradle:** phân biệt task `compileJava`, `compileTestJava` và task sinh mã. Nếu `compileJava` thiếu generated source, hãy kiểm tra dependency giữa generator task và source set. Trên dự án có wrapper, chạy đúng task như `./gradlew compileJava`; Windows dùng `gradlew.bat`. Đọc diagnostics do compiler in bên trong task, không cho rằng mọi stacktrace của Gradle đều là lỗi cú pháp Java.

**Maven:** phân biệt goal compile và testCompile của compiler plugin, xác định module đầu tiên thất bại trong reactor. Một module upstream không build có thể làm downstream bị skipped; điều đó không chứng minh downstream có lỗi source riêng. Kiểm tra dependency scope, plugin settings và source roots.

**IDE:** các dấu gạch đỏ có thể đến từ index, JDK cấu hình riêng hoặc generated files cũ. Đồng thời IDE có thể compile “xanh” nhờ cache mà command-line clean build vẫn hỏng. Tái hiện bằng toolchain và build command chính thức trước khi sửa hàng loạt source.

Nếu lỗi chỉ xuất hiện trong một môi trường, tìm **khác biệt về toolchain, dependency versions, generated files, OS/path separator và build caches** trước khi kết luận ngôn ngữ Java hoạt động khác.

## 11. Những cách sửa dễ làm che giấu nguyên nhân

- **Thêm mọi JAR vào classpath:** có thể hết lỗi symbol nhưng vô tình chọn nhầm version, gây duplicate classes và lỗi runtime.
- **Tạo class giả cùng tên generated type:** không giải quyết generator; có thể gây lỗi trùng hoặc API không khớp khi generator chạy lại.
- **Thêm public cho mọi field/method:** không giải quyết thiếu dependency hay type checking, lại thay đổi API surface.
- **Tắt warnings hoặc bỏ qua compiler errors:** chỉ làm mất tín hiệu kiểm tra; cần biết warning/error gốc và chính sách build.
- **Sửa tất cả dòng gạch đỏ trong một lượt:** khó chứng minh thay đổi nào đã giải quyết nguyên nhân và dễ tạo regression.
- **Tin vào compile incremental:** class output cũ có thể che lỗi producer. Thử build sạch đúng cơ chế dự án khi cần kiểm chứng.

Các sửa đổi an toàn thường có phạm vi nhỏ nhất phù hợp với nguyên nhân: một dependency edge, một dấu ngoặc, một signature API, một task dependency hoặc một source root.

## 12. Bài thực hành kiểm tra nguyên nhân và hậu quả

1. Tạo `Greeter.java` và `Main.java` như mục 3, biên dịch thiếu thư viện. Ghi lại các diagnostic nhắc tới `demo.lib` và `Greeter`, không cố định số lượng.
2. Không đổi source, biên dịch đủ hai file hoặc thêm đúng output thư viện vào compile classpath. Chạy và xác nhận dòng `HELLO, JAVA`.
3. Tạo `ParseFixed.java`, chạy ra `5`. Trên bản sao thử nghiệm, bỏ dấu `}` của method `add` và đọc parser errors. Khôi phục dấu ngoặc, biên dịch lại.
4. Với `OverloadFixed.java`, chạy ra `string`; đổi `accept((String) null)` thành `accept(null)` rồi quan sát ambiguity. Khôi phục cast.
5. Trong project thực tế, phân biệt một lỗi **generator** với nhiều lỗi **consumer**: sửa task/input của generator rồi xem các lỗi tìm type biến mất như thế nào.
6. Nếu còn lỗi sau một lần sửa, ghi riêng root cause mới. Không cố quy toàn bộ diagnostics về một lỗi duy nhất khi chúng độc lập.

**Điểm cần nhớ:** số dòng errors không phải số lượng lỗi gốc. Tìm khai báo, nguồn phụ thuộc hoặc bước build nằm upstream của nhiều diagnostics; thay đổi nhỏ có chứng cứ và biên dịch lại chính là cách kiểm chứng nguyên nhân, chứ không phải chỉ xóa từng thông báo trong IDE.
