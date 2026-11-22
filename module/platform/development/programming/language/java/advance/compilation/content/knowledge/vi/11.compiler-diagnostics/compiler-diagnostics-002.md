# Phân biệt lỗi cú pháp, tên, kiểu, truy cập và phụ thuộc khi biên dịch Java

## 1. Mục tiêu học tập

Khi chạy javac, dòng chữ error không đủ để biết phải sửa ở đâu. Nhiều lỗi có thông báo gần giống nhau nhưng thuộc các nguyên nhân khác nhau: có câu lệnh viết sai ngữ pháp, tên được viết đúng cú pháp nhưng compiler không tìm thấy khai báo, biểu thức dùng sai kiểu, thành viên tồn tại nhưng không được phép truy cập, hoặc một lớp/thư viện không có trong tập dependency dùng để biên dịch.

Bài này tập trung vào năm nhóm chẩn đoán:

1. **Lỗi cú pháp (syntax/parsing)**: chuỗi token không tạo thành một cấu trúc Java hợp lệ.
2. **Lỗi tên (name/symbol resolution)**: compiler không phân giải được tên lớp, biến, phương thức hoặc package trong ngữ cảnh đang xét.
3. **Lỗi kiểu (type checking)**: tên đã phân giải nhưng kiểu, tham số, giá trị trả về hoặc phép gán không tương thích.
4. **Lỗi truy cập (accessibility)**: khai báo có tồn tại nhưng không thể dùng từ vị trí gọi theo access modifier hoặc ranh giới module.
5. **Lỗi phụ thuộc (dependency/configuration)**: mã nguồn cần lớp/JAR/module nhưng compiler hay runtime không tìm được bản phù hợp.

Mục tiêu không phải học thuộc một bảng câu chữ cố định của javac, vì diagnostic có thể đổi theo JDK, mà là **truy ngược từ lỗi đến tầng kiểm tra và điều kiện cần khôi phục**. Cuối bài có dự án Java 17+ chạy được, thí nghiệm gây lỗi có chủ đích, quy trình chẩn đoán và bài tập tự kiểm tra.

## 2. Vì sao các nhóm lỗi liên quan nhưng khác nhau?

Hãy hình dung quá trình biên dịch ở mức khái quát:

~~~text
Tệp .java
   |
   v
Đọc ký tự, tách token, phân tích cú pháp
   |             Lỗi syntax: thiếu ;, }, token sai vị trí
   v
Phân giải tên và khai báo
   |             Lỗi name: cannot find symbol
   v
Kiểm tra kiểu và khả năng truy cập
   |             Lỗi type: incompatible types
   |             Lỗi access: private access / package not visible
   v
Phân tích luồng, kiểm tra các ràng buộc khác
   |             Ví dụ: missing return, uninitialized variable
   v
Tạo bytecode .class
   |
   v
JVM nạp và chạy .class
                 Lỗi runtime: NoClassDefFoundError, NoSuchMethodError...
~~~

Sơ đồ là **mô hình học tập**. Trong javac thực tế, phân giải tên, type attribution, accessibility và các kiểm tra ngữ nghĩa có thể đan xen; đừng hiểu chúng là năm chương trình con chạy lần lượt hoàn toàn độc lập. Cũng đừng đánh đồng **thông báo đầu tiên javac in ra** với nguyên nhân gốc duy nhất: một lỗi dependency có thể làm phát sinh hàng loạt cannot find symbol và incompatible types phía sau.

Bảng định hướng:

| Nhóm | Câu hỏi cần kiểm tra | Diagnostic thường gặp |
| --- | --- | --- |
| Cú pháp | Dấu ngoặc, dấu ;, vị trí token có hợp lệ? | ';' expected; reached end of file while parsing |
| Tên | Tên được khai báo trong scope/import/package đúng chưa? | cannot find symbol |
| Kiểu | Có chuyển/gán/gọi giữa các kiểu hợp lệ? | incompatible types; method cannot be applied to given types |
| Truy cập | Người gọi có quyền dùng kiểu/member đó không? | has private access; is not public; package ... is not visible |
| Phụ thuộc | Class/JAR/module có trên đúng compile/runtime path không? | package ... does not exist; module not found; NoClassDefFoundError |
| Kiểm tra khác | Đường điều khiển/exception/definite assignment hợp lệ? | missing return; unreachable statement; unreported exception |

**Phân loại là để tìm nguyên nhân, không phải để ép mỗi dòng lỗi vào đúng một ô duy nhất.** Ví dụ cannot find symbol có thể vì viết sai tên, nhưng cũng có thể vì thiếu JAR. Khi thiếu dependency, biểu hiện ở compiler đôi khi lại là một lỗi phân giải tên.

## 3. Chuẩn bị dự án Java 17 để so sánh

Tạo thư mục **diagnostics-lab** với hai tệp nguồn:

~~~text
diagnostics-lab/
└── src/
    └── demo/
        ├── api/
        │   └── Printer.java
        └── app/
            └── Main.java
~~~

Thư mục out sẽ tạo trước khi biên dịch. Hai lớp được đặt ở hai package khác nhau để thể hiện được vấn đề import và access.

### Tệp src/demo/api/Printer.java

~~~java
package demo.api;

public final class Printer {
    private Printer() {
    }

    public static String label(int count) {
        return "Count=" + count;
    }

    private static String internalLabel(int count) {
        return "Secret=" + count;
    }
}
~~~

Printer có public method label(int) trả String. internalLabel(int) tồn tại nhưng private, chỉ dùng nội bộ lớp Printer. Constructor private không ảnh hưởng tới việc gọi method static public.

### Tệp src/demo/app/Main.java

~~~java
package demo.app;

import demo.api.Printer;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String message = Printer.label(3);
        System.out.println(message);
    }
}
~~~

Main import đúng tên lớp Printer, truyền int cho label(int), nhận String và in ra. Hai file dùng cú pháp Java 17 hợp lệ.

### Lệnh biên dịch và chạy

Đặt terminal tại thư mục **diagnostics-lab**, nơi chứa src. Kiểm tra:

~~~sh
javac -version
java -version
~~~

Dùng JDK 17 trở lên. Tạo out theo shell đang dùng:

~~~bash
# Bash (Linux/macOS)
mkdir -p out
~~~

~~~powershell
# Windows PowerShell
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Biên dịch cả hai tệp:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

Chạy:

~~~sh
java -cp out demo.app.Main
~~~

**Stdout chính xác của mã gốc:**

~~~text
Count=3
~~~

Đầu ra bytecode có:

~~~text
out/
└── demo/
    ├── api/
    │   └── Printer.class
    └── app/
        └── Main.class
~~~

Trong các thí nghiệm dưới đây, **chỉ sửa dòng được nêu rồi biên dịch lại**. Mỗi thí nghiệm bắt đầu từ phiên bản hai tệp gốc ở trên; hoàn nguyên thay đổi trước khi thử lỗi tiếp theo. Các đoạn lỗi là mã **cố tình không biên dịch**, không phải ví dụ chạy độc lập.

## 4. Nhóm 1 — Lỗi cú pháp: compiler chưa hiểu cấu trúc câu lệnh

Đặc trưng: compiler chưa tạo được cây cú pháp hợp lệ từ chuỗi token ở một phần nguồn. Những thiếu sót thường gặp gồm thiếu dấu chấm phẩy, thiếu ngoặc, ký tự đặt sai vị trí, dấu nháy không đóng, chuỗi escape sai hoặc từ khóa dùng không hợp ngữ pháp.

### Ví dụ 1: thiếu dấu chấm phẩy

Trong Main.java, sửa:

~~~java
String message = Printer.label(3)
System.out.println(message);
~~~

Dòng khai báo biến thiếu dấu ;. javac thường báo thông điệp dạng **';' expected** tại vị trí nó cần dấu kết thúc. Sửa thành:

~~~java
String message = Printer.label(3);
System.out.println(message);
~~~

**Vì sao đây là lỗi cú pháp?** Chưa cần xét Printer có tồn tại, method có public hay kiểu String có đúng: cách tổ chức câu lệnh đã không hợp ngữ pháp Java.

### Ví dụ 2: thiếu dấu đóng ngoặc nhọn

Nếu xóa một dấu } cuối class, javac có thể báo dạng **reached end of file while parsing**. Vị trí lỗi đôi khi nằm **ở cuối file**, không phải ngay nơi bạn vô tình thiếu dấu. Khi thấy lỗi này, đối chiếu cặp { }, ( ), [ ], và kiểm tra các khối class/method/if/try vừa sửa.

### Ví dụ 3: token đặt sai vị trí

~~~java
int value = ;
~~~

Biểu thức sau dấu = bị bỏ trống. Diagnostic có thể nêu illegal start of expression. Không sửa theo kiểu ép biến thành String hay thêm import: phải bổ sung một biểu thức hợp lệ, ví dụ int value = 3;.

### Cách chẩn đoán lỗi cú pháp

- Bắt đầu từ **dòng đầu tiên có diagnostic về parsing**, nhưng kiểm tra cả dòng phía trước: lỗi có thể xuất hiện ở token sau vị trí thiếu thật.
- Xác nhận cặp dấu ngoặc, dấu chấm phẩy, dấu nháy, cấu trúc khai báo và từ khóa.
- Sửa một lỗi cấu trúc trước, biên dịch lại. Một dấu } thiếu có thể làm compiler báo nhiều lỗi dây chuyền.
- Khi mã mới copy từ trang web, kiểm tra ký tự nháy cong hoặc ký tự Unicode thay thế dấu " hay ' thông thường.

Compiler **không sửa hộ cú pháp** dù IDE có thể gợi ý; diagnostic giúp tìm nơi cần sửa trong source.

## 5. Nhóm 2 — Lỗi tên: cannot find symbol

Lỗi tên xuất hiện khi compiler hiểu một biểu thức hoặc lời gọi về mặt ngữ pháp nhưng không tìm thấy khai báo phù hợp trong scope, import hoặc tập kiểu nhìn thấy.

### Ví dụ 1: sai tên method

Trong Main.java, viết:

~~~java
String message = Printer.lable(3);
~~~

Printer có method tên label, không có lable. javac thường báo dạng:

~~~text
cannot find symbol
  symbol:   method lable(int)
  location: class demo.api.Printer
~~~

Đoạn trên minh họa phần chính của diagnostic, không cam kết vị trí/căn lề/dòng chính xác của mọi bản javac.

**Cách sửa:** đổi lable thành label. Đã xác định được class Printer, nên bước đầu tiên là kiểm tra tên và chữ ký method của Printer chứ không vội chỉnh classpath.

### Ví dụ 2: biến ngoài scope

~~~java
if (true) {
    int count = 3;
}
System.out.println(count); // LỖI: count ngoài scope
~~~

Biến count được khai báo bên trong block if. Bên ngoài block đó, tên không còn nằm trong scope; compiler có thể báo cannot find symbol cho variable count. Sửa bằng cách khai báo biến ở scope thích hợp và bảo đảm definite assignment trước khi đọc.

### Ví dụ 3: tên lớp không tìm thấy

Nếu xóa dòng:

~~~java
import demo.api.Printer;
~~~

mà vẫn dùng tên ngắn Printer trong package demo.app, compiler không tự tìm trong package demo.api. Sửa bằng cách khôi phục import hoặc sử dụng tên đầy đủ demo.api.Printer.

**Lưu ý:** lỗi cannot find symbol không luôn có nghĩa “viết sai chính tả”. Nó còn có thể do class nằm trong dependency chưa được đưa vào compile classpath, package bị đặt sai, nguồn chưa được compile, hoặc code được viết cho một API/phiên bản khác.

### Quy trình cho lỗi tên

1. Đọc phần **symbol**: đang thiếu variable, class hay method? Có tham số/kiểu cụ thể không?
2. Đọc phần **location**: compiler đang tìm method trong class nào, hoặc tên trong scope nào?
3. Kiểm tra chính tả và chữ hoa/thường, import, package, phạm vi block và khai báo thật.
4. Nếu class chưa được compiler nhìn thấy, chuyển sang kiểm tra **phụ thuộc và classpath**; không tạo một biến hoặc method giả chỉ để làm lỗi biến mất.

## 6. Nhóm 3 — Lỗi kiểu: tên có thể đúng nhưng phép dùng không hợp lệ

Java kiểm tra kiểu tĩnh. Một method có thể tồn tại và truy cập được, nhưng lời gọi vẫn sai nếu danh sách tham số, kiểu generic, giá trị trả về hoặc phép gán không hợp lệ.

### Ví dụ 1: truyền String thay vì int

Main.java gọi:

~~~java
String message = Printer.label("3");
~~~

Method đã khai báo label(int), còn "3" là String. Compiler sẽ báo lỗi về **String cannot be converted to int**, hoặc method không áp dụng được với kiểu tham số đã truyền, tùy cách hiển thị diagnostic.

**Cách sửa đúng:** truyền một int thực sự:

~~~java
String message = Printer.label(3);
~~~

Nếu dữ liệu bắt đầu từ text do người dùng nhập, cần chuyển có kiểm tra:

~~~java
int count = Integer.parseInt("3");
String message = Printer.label(count);
~~~

Đoạn chuyển đổi có thể ném NumberFormatException nếu chuỗi không phải số nguyên hợp lệ. Việc qua được type checking **không bảo đảm input runtime hợp lệ**.

### Ví dụ 2: kiểu kết quả không gán được

~~~java
int result = Printer.label(3); // LỖI: method trả String
~~~

Compiler có thể báo incompatible types: String cannot be converted to int. Lỗi không nằm ở import, vì method đã được tìm thấy. Hãy đổi biến nhận sang String hoặc thay đổi thiết kế API nếu thực sự cần số nguyên.

### Ví dụ 3: generic invariance

~~~java
java.util.List<String> texts = java.util.List.of("a", "b");
java.util.List<Object> values = texts; // LỖI BIÊN DỊCH
~~~

Dù String là subtype của Object, List<String> **không** là subtype của List<Object>. Nếu được phép gán như vậy, ta có thể thêm Integer vào một danh sách được kỳ vọng chỉ chứa String. Tùy mục tiêu, có thể dùng List<? extends Object> để đọc với giới hạn tương ứng, hoặc tạo danh sách mới:

~~~java
java.util.List<Object> values =
        new java.util.ArrayList<>(texts);
~~~

Đoạn này hợp lệ với generic inference phù hợp, tạo danh sách riêng để thêm các Object khác nếu cần.

### Ví dụ 4: overloaded method và ambiguity

Nếu nhiều overload cùng phù hợp nhưng không có lựa chọn duy nhất tốt nhất, compiler có thể báo **reference to ... is ambiguous**. Không nên coi đây là cannot find symbol: method có thể được tìm thấy **quá nhiều ứng viên tương đương**. Khắc phục bằng cách chọn kiểu tham số chính xác, overload ít gây mơ hồ hơn hoặc cast có chủ đích nếu thật sự cần.

### Cách chẩn đoán lỗi kiểu

- Đọc **required** và **found** (hoặc inferred type/actual argument list) trong output chi tiết.
- So sánh từng kiểu tham số với từng đối số theo đúng thứ tự.
- Kiểm tra kiểu trả về của method, generic type arguments, boxing/unboxing, primitive conversions.
- Không tự sửa bằng ép kiểu mù quáng. Cast có thể qua compile nhưng gây ClassCastException lúc chạy.
- Nếu API dependency đã đổi chữ ký, xem lại **phiên bản dependency** trước khi sửa logic.

## 7. Nhóm 4 — Lỗi truy cập: member có tồn tại nhưng không dùng được

Lỗi truy cập khác lỗi tên: compiler có thể tìm được khai báo, nhưng **ngữ cảnh gọi không có quyền sử dụng**.

### Ví dụ 1: gọi private method ở class khác

Trong Printer.java, internalLabel(int) là private. Nếu Main.java gọi:

~~~java
String message = Printer.internalLabel(3);
~~~

javac báo dạng:

~~~text
internalLabel(int) has private access in demo.api.Printer
~~~

Điểm khác biệt với trường hợp lable là: **method thật sự tồn tại**, nhưng private ngăn Main truy cập.

Cách sửa theo thiết kế tốt: gọi public API Printer.label(3). Chỉ chuyển internalLabel thành public nếu thực sự muốn đưa nó vào hợp đồng API, vì thay access modifier ảnh hưởng thiết kế lớp và các client về sau.

### Các mức truy cập thường gặp

| Modifier | Nguyên tắc ở mức ngôn ngữ Java |
| --- | --- |
| public | Có thể truy cập từ nơi khác nếu các điều kiện khác như module readability/exports cũng thỏa |
| protected | Truy cập trong cùng package và từ subclass ở package khác theo các quy tắc protected cụ thể |
| Không ghi modifier | Package-private: chỉ code trong cùng package phù hợp được sử dụng |
| private | Phạm vi truy cập riêng theo quy tắc private/nestmates của Java; không mở cho class khác bất kỳ |

**Đừng nhầm package với thư mục:** hai class có tên package giống nhau về mặt Java không đơn thuần là “nằm trong cùng thư mục”. Package declaration, module và runtime environment đều quan trọng.

### Ví dụ 2: package của named module không export

Trong JPMS, một class public nằm trong package không export của module đích vẫn có thể **không truy cập được** từ named module khác. Sơ đồ minh họa descriptor:

~~~java
// module-info.java của module library
module demo.library {
    exports demo.api;
}
~~~

Nếu một module khác requires demo.library rồi import một public class trong demo.internal (không export), compiler có thể báo package ... is not visible hoặc does not export package. Đây là **lỗi ranh giới module**, không phải vì class thiếu public.

Descriptor trên chỉ để minh họa; muốn chạy độc lập cần tổ chức các source của hai module, một module consumer và các class tương ứng.

**Cách sửa:** ưu tiên public API nằm trong package được export, hoặc thay descriptor exports có chủ đích. Khai báo requires tạo quan hệ đọc nhưng **không tự export mọi package** của dependency. Khi lỗi liên quan reflection sâu, có thể cần opens chứ không phải exports; mục tiêu của hai khai báo khác nhau.

## 8. Nhóm 5 — Lỗi phụ thuộc: code đúng nhưng thiếu class/JAR/module phù hợp

**Dependency** là lớp, thư viện hoặc module mà source cần để biên dịch và/hoặc chương trình cần lúc chạy. Thiếu dependency có thể biểu hiện như lỗi package không tồn tại hoặc cannot find symbol, nhưng nguyên nhân thực là **tập đầu vào compiler/runtime không đầy đủ**.

### Trường hợp A: chỉ biên dịch Main mà compiler không thấy Printer

Từ gốc diagnostics-lab, nếu chạy:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/app/Main.java
~~~

trong cấu hình chưa có Printer trên compiler classpath/sourcepath, javac không tìm được demo.api.Printer. Diagnostic có thể gồm **package demo.api does not exist** và **cannot find symbol Printer**.

Đây là lỗi thiếu **nguồn hoặc class phụ thuộc trong đường tìm kiếm**. Nó có thể trông như lỗi tên; phải xem Printer.java đã tồn tại và có đúng package hay chưa.

Cách đơn giản nhất là liệt kê cả hai tệp như phần 3:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

Hoặc nếu Printer.class đã được biên dịch trong out, biên dịch Main riêng với classpath:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/app/Main.java
~~~

Hai tùy chọn có vai trò khác nhau:

- **-cp out** (đối với javac) giúp compiler tìm lớp đã biên dịch thuộc dependency.
- **-d out** chọn nơi ghi .class mới. Nó không tự bổ sung out vào compiler classpath.

### Trường hợp B: compile thành công, runtime thiếu Printer

Giả sử Main.class được biên dịch khi Printer hiện diện, nhưng lúc chạy thiếu Printer.class trong runtime classpath (hoặc JAR của Printer bị bỏ khỏi bản đóng gói). JVM có thể ném **NoClassDefFoundError** khi cần nạp Printer. Đây là lỗi runtime, không phải javac syntax error.

Tương tự, **ClassNotFoundException** thường xuất hiện khi một API nạp lớp theo tên (như Class.forName) không tìm được class. Hai loại có liên quan nhưng là API/điểm báo lỗi khác nhau; không nên dùng chúng như một nhãn duy nhất.

### Trường hợp C: class có nhưng phiên bản API khác

Một client đã biên dịch với method label(int), nhưng runtime lại nạp bản Printer.class không còn method tương thích nhị phân. Khi bytecode cố gọi descriptor cũ, JVM có thể báo **NoSuchMethodError**. Hãy kiểm tra dependency version và artifact runtime, xây dựng lại các module phù hợp; đừng sửa chính tả trong source khi lỗi phát sinh do bộ .class/JAR không khớp.

### Trường hợp D: JDK và bytecode không tương thích

Nếu JDK mới sinh bytecode có class-file version lớn hơn JVM đang chạy hỗ trợ, runtime báo **UnsupportedClassVersionError**. Lệnh --release 17 trong ví dụ giới hạn bytecode/API nền tảng của source theo Java 17. Nó **không tự làm cho một JAR bên ngoài đã biên dịch bằng Java mới hơn trở nên tương thích Java 17**.

Kiểm tra java -version, javac -version, cấu hình toolchain và phiên bản class của dependency.

### Trường hợp E: module path và classpath bị dùng lẫn

Với explicit named modules, compiler/runtime phải phân giải dependency trên module path thích hợp và descriptor phải khai báo requires; package công khai phải có exports phù hợp. Đặt một JAR vào classpath hoặc module path **không luôn có cùng tác động**.

Khi javac nói module not found hoặc package is not visible, kiểm tra module-info.java, tên module, module path, requires và exports. Khi chỉ dùng classpath bình thường, kiểm tra compile/runtime -cp và cấu trúc .class/JAR.

## 9. Phân biệt lỗi lúc compile và lúc chạy

| Giai đoạn | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Trước/đang javac | ';' expected | Parser không hiểu nguồn |
| Đang javac | cannot find symbol | Compiler không phân giải tên |
| Đang javac | incompatible types | Kiểu đối số/giá trị không hợp lệ |
| Đang javac | has private access | Không có quyền truy cập method |
| Đang javac | package ... does not exist | Có thể thiếu nguồn/import/classpath |
| Khi JVM khởi động | Could not find or load main class | Sai main class name hoặc runtime classpath/module configuration |
| Khi JVM nạp/liên kết lớp | NoClassDefFoundError | Thiếu class dependency đã từng cần đến khi compile/link |
| Khi JVM liên kết lời gọi | NoSuchMethodError | Method descriptor runtime khác giả định của caller |
| Khi JVM kiểm tra phiên bản .class | UnsupportedClassVersionError | Bytecode mới hơn runtime có thể xử lý |
| Khi code chạy | NumberFormatException, NullPointerException | Dữ liệu hoặc điều kiện thực tế không hợp lệ |

**Quan trọng:** javac có thể báo lỗi nhưng thư mục out vẫn còn .class từ lần biên dịch trước. Nếu lập tức chạy java, có thể bạn đang chạy **bản cũ**, dẫn đến kết luận sai rằng code lỗi vẫn chạy. Khi thử nghiệm, hãy chắc chắn javac thành công từ source hiện tại và java dùng đúng output.

Không phải lỗi runtime nào cũng là “dependency error”; ví dụ NullPointerException có thể do logic hoặc dữ liệu. Ngược lại, một lỗi liên quan dependency có thể xuất hiện **ngay tại compile-time** nếu javac không nhìn thấy class được import.

## 10. Cách đọc một diagnostic javac đúng cách

Ví dụ minh họa khi gọi method sai:

~~~text
src/demo/app/Main.java:...
error: cannot find symbol
    String message = Printer.lable(3);
                            ^
  symbol:   method lable(int)
  location: class demo.api.Printer
~~~

Không dựa vào số dòng hoặc vị trí dấu ^ trong ví dụ minh họa này, vì output thực tế có thể khác giữa phiên bản javac. Hãy rút ra các thông tin quan trọng:

- **File/line**: source đang được javac xử lý và vị trí cần xem.
- **Error message**: loại vấn đề mà compiler phát hiện.
- **Symbol/required/found/location**: tên hoặc kiểu cụ thể để đối chiếu.
- **Các lỗi đầu tiên có ý nghĩa**: nguồn lỗi gây ra các diagnostic kéo theo.

Mọi dòng diagnostic đều cần đọc, nhưng **không nhất thiết phải sửa đồng thời mọi dòng**. Nếu parser thiếu một dấu } hoặc một dependency JAR, sửa đúng nguyên nhân đó có thể làm biến mất nhiều lỗi tiếp theo.

### Bật diagnostic chi tiết

Khi compiler hỗ trợ, thêm tùy chọn:

~~~sh
javac -Xdiags:verbose -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

Tùy chọn -Xdiags:verbose giúp xem diagnostic chi tiết hơn trong một số tình huống như overload và kiểu generic. Đây là công cụ **quan sát**, không phải chế độ sửa lỗi tự động.

Để xem cảnh báo tiềm ẩn:

~~~sh
javac -Xlint:all -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
~~~

-Xlint:all bật các nhóm lint warning được javac hỗ trợ. Cảnh báo không đồng nghĩa với lỗi compile: javac vẫn có thể tạo .class khi chỉ có warning. Tùy chọn **-Werror** có thể chuyển điều kiện “có warning” thành build failure; chỉ dùng khi chính sách dự án yêu cầu.

### Exit code và công cụ build

Thông thường javac trả exit code khác 0 khi biên dịch thất bại. Trong CI, Maven, Gradle hoặc IDE, hãy tìm **lệnh javac hoặc diagnostic gốc** bên dưới thông báo “build failed”. Lỗi wrapper không tự cho biết bạn gặp syntax, type hay dependency; thông báo gốc mới giúp định vị.

Khi cần kiểm tra lệnh compiler mà build tool thực sự dùng, hãy xem compiler arguments/verbose logging của công cụ đó theo mức độ phù hợp. Đặc biệt chú ý JDK toolchain, source roots, classpath/module path và các annotation processors.

## 11. Cây quyết định chẩn đoán

~~~text
javac thất bại
    |
    +-- Không hiểu token/cấu trúc? (';' expected, parsing ...)
    |      -> Kiểm tra cú pháp và dấu ngoặc.
    |
    +-- Tên không phân giải được? (cannot find symbol)
    |      -> Kiểm tra scope, import, tên API.
    |      -> Nếu class phụ thuộc thiếu: kiểm tra compile classpath/module path.
    |
    +-- Tên có nhưng kiểu không khớp? (incompatible types)
    |      -> Đối chiếu required/found, signature, generics, overload.
    |
    +-- Tên có nhưng không dùng được? (private access/not exported)
    |      -> Kiểm tra modifier, package, requires/exports.
    |
    +-- Module/JAR không tìm được?
    |      -> Kiểm tra phiên bản, source roots, dependency artifact/path.
    |
    v
Biên dịch thành công
    |
    +-- java không tìm main class?
    |      -> Kiểm tra tên đầy đủ và runtime classpath/module path.
    |
    +-- Runtime thiếu class/method?
    |      -> Kiểm tra class/JAR hiện diện và binary compatibility.
    |
    v
Chạy test để xác nhận hành vi
~~~

Cây này phục vụ thao tác thực tế; không phải mọi diagnostic có ranh giới hoàn toàn độc lập. Ví dụ lỗi access có thể xảy ra trong quá trình phân giải member, và lỗi dependency có thể hiện dưới dạng cannot find symbol. Hãy kiểm tra **nguyên nhân sâu nhất hợp lý với mã nguồn và cấu hình**.

## 12. Chẩn đoán theo nguyên nhân gốc, không theo triệu chứng

### Tình huống 1: đổi tên method nhưng dependency chưa được nâng cấp

Code client gọi Printer.label(3). Nếu source của Printer bản đang compile chỉ có method format(int), có thể javac báo cannot find symbol: method label(int). Đây là lỗi tên **theo API đang được compiler nhìn thấy**, nhưng nguyên nhân nghiệp vụ có thể là client và library lệch version. Trước khi tạo lại method hoặc sửa code, kiểm tra API contract và dependency version mong muốn.

### Tình huống 2: thiếu import và thiếu JAR trông khá giống nhau

- Nếu Printer có trên compile classpath nhưng thiếu import demo.api.Printer và không dùng tên đầy đủ, sửa import có thể đủ.
- Nếu Printer hoàn toàn không nằm trong compile classpath/sourcepath, thêm import cũng không giúp compiler tìm class.

Vì vậy phải kiểm tra cả **khai báo nguồn** và **sự hiện diện của dependency**, thay vì thử import một cách mù quáng.

### Tình huống 3: private method không nên “sửa” bằng public bừa bãi

Lỗi private access không chứng minh class được thiết kế sai. Rất có thể caller đang dùng API nội bộ. Hãy tìm public method phục vụ đúng công việc, hoặc thiết kế một public façade có hợp đồng rõ ràng. Tự chuyển mọi member thành public chỉ để javac im lỗi sẽ làm hỏng encapsulation.

### Tình huống 4: cast để hết lỗi kiểu

Nếu javac báo String cannot be converted to int, thêm một cast ép Object/String về Integer có thể làm code biên dịch trong vài cấu hình, nhưng dễ gây ClassCastException lúc chạy. Việc xử lý đúng có thể là parse dữ liệu text thành số với validation. Compile pass chỉ chứng minh tuân thủ quy tắc kiểu tĩnh, không chứng minh dữ liệu runtime hợp lệ.

### Tình huống 5: sai package hoặc sai root classpath

Một source Java có khai báo package demo.api nhưng lớp được chạy từ classpath root không đúng có thể phát sinh lỗi tìm lớp runtime. Hãy phân biệt:

~~~text
Tên lớp: demo.app.Main
Tệp .class: out/demo/app/Main.class
Classpath root: out
Lệnh: java -cp out demo.app.Main
~~~

Không đặt classpath thành out/demo/app rồi kỳ vọng JVM tự bỏ qua các phần của package name.

## 13. Các lỗi bổ sung dễ bị phân loại nhầm

Ngoài năm nhóm chính, Java còn nhiều ràng buộc ngôn ngữ quan trọng:

| Chẩn đoán | Nguyên nhân thật |
| --- | --- |
| variable ... might not have been initialized | **Definite assignment**: một đường đi tới điểm đọc chưa gán biến |
| unreachable statement | **Reachability**: không có đường điều khiển hợp lệ tới câu lệnh |
| missing return statement | Phương thức có thể kết thúc bình thường mà thiếu giá trị return |
| unreported exception ... must be caught or declared | Checked exception chưa catch hoặc khai báo throws |
| class X is public, should be declared in a file named X.java | Quy tắc tên file của public top-level class |
| reference to method is ambiguous | Overload resolution không chọn được ứng viên duy nhất |
| variable X is already defined | Khai báo trùng tên trong scope không cho phép |
| bad class file / class file has wrong version | Input class file/dependency không tương thích hoặc không đọc được |

Không nên gọi tất cả các lỗi này là syntax. Nhiều đoạn mã **đúng cú pháp** nhưng vi phạm kiểm tra ngữ nghĩa/luồng hoặc quy tắc tổ chức tệp.

### Ví dụ definite assignment

~~~java
int count;
if (args.length > 0) {
    count = 3;
}
System.out.println(count); // Có đường chưa gán count
~~~

Đây không phải lỗi do từ khóa int hay tên count sai. Compiler phân tích các đường điều khiển và nhận thấy khi args.length == 0, count chưa được gán. Sửa bằng cách khởi tạo, thêm else hoặc thay đổi luồng xử lý phù hợp nghiệp vụ.

## 14. Thực hành: mỗi lần thay đúng một nguyên nhân

Bắt đầu từ hai tệp hợp lệ ở phần 3, giữ bản gốc để dễ hoàn nguyên. Với từng thí nghiệm, dự đoán trước **compile sẽ pass hay fail**, nhóm lỗi, sau đó chạy javac và đọc diagnostic.

1. **Syntax:** xóa dấu ; sau Printer.label(3). Vì sao compiler chưa cần kiểm tra kiểu để phát hiện lỗi?
2. **Name:** đổi label thành lable. Compiler đã tìm thấy class nào? Tên method nào không có?
3. **Type:** truyền "3" thay vì 3. So sánh kiểu actual với required.
4. **Access:** thay label thành internalLabel. Vì sao method có thật nhưng Main không được gọi?
5. **Dependency:** chỉ biên dịch Main từ gốc dự án khi chưa cấu hình Printer trong compile classpath/sourcepath. Vì sao thêm import không giải quyết được?
6. **Runtime dependency:** giả sử runtime đóng gói thiếu Printer.class dù compile đã thành công. Lỗi xảy ra ở javac hay JVM?
7. **Mismatch phiên bản:** client đã compile với API cũ nhưng runtime nhận bản thư viện thay chữ ký. Loại lỗi nào có thể xuất hiện?
8. **Đầu ra cũ:** sửa code nhưng không compile lại, sau đó chạy java. Tại sao stdout có thể vẫn phản ánh bản trước?

Với lỗi cú pháp/tên/kiểu/truy cập, sau khi đã sửa về bản hợp lệ, chạy lại:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/api/Printer.java src/demo/app/Main.java
java -cp out demo.app.Main
~~~

Kỳ vọng output luôn trở về:

~~~text
Count=3
~~~

Đừng chạy thử nhiều phiên bản lỗi trong cùng source rồi cố gán mọi diagnostic cho một thay đổi: khi compiler gặp nhiều lỗi, một lỗi có thể che lấp hoặc dẫn đến lỗi khác.

## 15. Checklist xử lý lỗi khi làm dự án thực tế

Trước khi sửa code, tự trả lời:

- **Lỗi xuất hiện ở javac hay JVM?** Có .class mới được tạo thành công hay đang chạy output cũ?
- **Diagnostic đầu tiên nói gì?** Phân tích cú pháp, không phân giải tên, sai kiểu, không có quyền, hay không tìm được artifact?
- **Compiler đang nhìn thấy source và dependency nào?** Có đúng package, API version, JDK và compile classpath/module path không?
- **Caller có quyền dùng API đó không?** Kiểm tra public/private, package, requires và exports.
- **Kiểu required/found có chính xác không?** Có generic, overload hoặc conversion làm thay đổi lời gọi không?
- **Runtime dùng cùng bộ JAR/.class với compile không?** Có binary mismatch, thiếu class hoặc JDK runtime cũ không?
- **Cách sửa có hợp đồng nghiệp vụ hợp lý không?** Không thêm cast, public hay fallback tùy tiện chỉ để hết error.
- **Đã biên dịch lại và kiểm thử chưa?** Xác nhận lệnh javac thành công và lệnh java chạy đúng artifact mới.

### Bảng nhớ nhanh

| Thấy diagnostic | Hỏi đầu tiên | Hướng sửa thường đúng |
| --- | --- | --- |
| ';' expected | Dấu hoặc cấu trúc nào bị thiếu? | Sửa cú pháp |
| cannot find symbol | Tên nào, trong scope/class nào? | Sửa tên/import/scope hoặc thiếu dependency |
| incompatible types | Required và actual khác nhau ở đâu? | Dùng đúng kiểu/API/chuyển đổi có kiểm tra |
| has private access | Vì sao caller không có quyền? | Dùng API public phù hợp, giữ encapsulation |
| package ... does not exist | Package sai hay dependency chưa được nhìn thấy? | Kiểm tra nguồn, compile classpath/module path |
| NoClassDefFoundError | Runtime thiếu class nào? | Kiểm tra runtime artifact/classpath |
| NoSuchMethodError | Client và thư viện có cùng binary contract không? | Đối chiếu version/rebuild nhất quán |
| UnsupportedClassVersionError | Runtime có hỗ trợ class-file version không? | Chọn toolchain và --release phù hợp |

## 16. Tự đánh giá

Bạn đã nắm bài nếu có thể giải thích:

1. Vì sao thiếu dấu ; là lỗi cú pháp còn viết nhầm lable là lỗi tên.
2. Vì sao truyền String vào label(int) là lỗi kiểu dù method tồn tại và public.
3. Vì sao private access khác với cannot find symbol.
4. Vì sao package does not exist có thể là một **triệu chứng của dependency** thay vì tên package sai.
5. Vì sao compile thành công không đảm bảo runtime classpath đầy đủ.
6. Vì sao -d out và -cp out phục vụ hai mục đích khác nhau.
7. Vì sao một lỗi đầu tiên có thể kéo theo nhiều diagnostic khác.
8. Vì sao sửa lỗi compiler phải đi kèm kiểm tra hợp đồng API và kết quả chạy.

### Tài liệu để đọc sâu

- **Java Language Specification (JLS)**: lexical structure, syntax, names, types, access control và definite assignment.
- Tài liệu chính thức **javac** của đúng JDK đang dùng: các tùy chọn -cp/--class-path, --module-path, --release, -Xdiags và -Xlint.
- **Java Virtual Machine Specification** và tài liệu Java launcher: nạp/liên kết class, class-file version và các lỗi liên kết.
- **Java Platform Module System (JPMS)**: requires, exports, module resolution cho chương trình dùng named modules.

Mỗi lần gặp lỗi, hãy phân biệt **mã có được viết đúng cú pháp, tên có được tìm thấy, kiểu có tương thích, quyền truy cập có hợp lệ, và dependency có hiện diện đúng phiên bản**. Phân loại như vậy giúp sửa **nguyên nhân** thay vì chỉ xóa thông báo lỗi.
