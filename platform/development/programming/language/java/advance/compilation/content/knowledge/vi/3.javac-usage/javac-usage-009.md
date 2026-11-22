# Phân biệt javac với chế độ chạy trực tiếp tệp nguồn của java

Java có hai cách phổ biến để chạy một chương trình viết trong tệp **.java**:

1. **Biên dịch trước bằng javac**, tạo tệp **.class**, sau đó chạy lớp đã biên dịch bằng **java**.
2. **Chạy thẳng tệp nguồn bằng java**, thường gọi là **source-file mode** hoặc **source-code launcher**: lệnh **java** tự biên dịch nguồn khi khởi chạy rồi thực thi chương trình.

Hai cách đều thực thi mã Java qua JVM. Khác biệt nằm ở **quy trình biên dịch, vị trí lưu sản phẩm biên dịch, cách quản lý phụ thuộc, khả năng tái sử dụng và mức kiểm soát build**. Chế độ chạy trực tiếp nguồn được giới thiệu từ **Java 11** (JEP 330); ví dụ cơ bản dưới đây tương thích **Java 17+**. Những khả năng mở rộng ở Java mới hơn được phân biệt ở phần 8.

## 1. Hiểu đúng vai trò của hai lệnh

**javac** là trình biên dịch Java. Nó đọc mã nguồn, kiểm tra cú pháp/kiểu và biên dịch thành bytecode nằm trong các tệp **.class**. Nếu biên dịch thành công, các class file có thể được chạy nhiều lần mà không cần biên dịch lại khi nguồn không đổi.

**java** là trình khởi chạy (launcher) chương trình. Khi chỉ định **tên lớp**, nó tìm và nạp class đã biên dịch để JVM thực thi. Khi chỉ định **đường dẫn tệp .java** trong source-file mode, chính launcher chủ động gọi cơ chế biên dịch trong bộ nhớ trước khi chạy. Vì thế **java Hello.java** vẫn có bước biên dịch, chỉ là bước đó được tích hợp trong một lệnh.

Đặt cạnh nhau:

~~~text
Biên dịch trước:
Hello.java --[javac -d out]--> out/Hello.class --[java -cp out Hello]--> JVM --> Kết quả

Chạy tệp nguồn:
Hello.java --[java Hello.java]--> biên dịch phục vụ lần chạy (trong bộ nhớ)
                                  --> JVM --> Kết quả
~~~

Đặc biệt, **java Hello** và **java Hello.java** mang ý nghĩa khác nhau:

- **java Hello**: khởi chạy lớp có tên **Hello** đã được biên dịch và tìm thấy trên classpath (hoặc cấu hình module tương ứng).
- **java Hello.java**: đọc **tệp nguồn Hello.java**, biên dịch để chạy, rồi khởi chạy lớp entry point của nguồn đó.

**java** có thể chạy tên lớp, JAR, named module hoặc tệp nguồn; chỉ hình thức **java File.java** được bàn tới ở chế độ source-file trong bài này.

## 2. Ví dụ chạy được trên Java 17+: cùng một nguồn, hai lộ trình

Tạo tệp **Hello.java** trong một thư mục mới:

~~~java
public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Xin chào, " + name + "!");
    }
}
~~~

### Cách A — Dùng javac rồi java

Từ thư mục chứa **Hello.java**, chạy:

~~~bash
javac -d out Hello.java
java -cp out Hello Mai
~~~

Kết quả chuẩn:

~~~text
Xin chào, Mai!
~~~

Sau lệnh **javac -d out Hello.java**, trên máy có thêm tệp **out/Hello.class** (dấu phân tách thư mục tùy hệ điều hành). Tùy chọn **-d out** chỉ thư mục nhận class file; **-cp out** cho launcher biết nơi tìm lớp đã biên dịch. **Hello** ở lệnh thứ hai là tên lớp, không phải tên tệp nguồn. **Mai** là tham số chương trình, đi vào **args[0]**.

Có thể chạy tiếp:

~~~bash
java -cp out Hello An
~~~

Kết quả:

~~~text
Xin chào, An!
~~~

Lần chạy sau **không tự gọi lại javac**. Nó tiếp tục dùng class đã có trong **out**. Nếu sửa **Hello.java** nhưng chưa biên dịch lại, **java -cp out Hello** vẫn thực thi bytecode cũ.

### Cách B — Dùng java chạy trực tiếp nguồn

Vẫn từ thư mục chứa **Hello.java**, chạy:

~~~bash
java Hello.java Mai
~~~

Kết quả chuẩn:

~~~text
Xin chào, Mai!
~~~

Lệnh này tự xử lý phần biên dịch cần cho lần chạy rồi khởi chạy chương trình. Trong chế độ source-file chuẩn, launcher **không tạo tệp Hello.class ở thư mục nguồn** để tái sử dụng như khi chạy javac. Nếu thư mục mới chưa có class file, sau **java Hello.java** sẽ không xuất hiện một **Hello.class** được ghi bởi lệnh đó.

Chạy lại:

~~~bash
java Hello.java An
~~~

Kết quả:

~~~text
Xin chào, An!
~~~

Mỗi lần khởi chạy bằng source-file mode, launcher thực hiện lại quá trình biên dịch cần thiết; không nên coi đây là cơ chế build có artifact dùng lại. Nếu sửa mã nguồn giữa hai lần chạy, lần chạy tiếp theo dùng nội dung nguồn đã sửa, miễn mã hợp lệ.

**Điểm học tập:** stdout và hành vi của chương trình có thể giống hệt nhau; điều phân biệt là **quy trình tạo và sử dụng bytecode**.

## 3. Bảng so sánh thực hành

| Tiêu chí | javac rồi java tên lớp | java chạy tệp nguồn |
| --- | --- | --- |
| Câu lệnh điển hình | javac -d out Hello.java; java -cp out Hello | java Hello.java |
| Đầu vào để bắt đầu | Tệp nguồn cho javac; tên lớp cho java | Đường dẫn tệp nguồn cho launcher |
| Biên dịch | Tường minh, do javac thực hiện | Ngầm khi launcher chuẩn bị chạy |
| Tệp .class đầu ra | Có, được ghi xuống đĩa theo cấu hình | Class dùng để chạy được biên dịch trong bộ nhớ; không xuất tệp .class để tái sử dụng |
| Những lần chạy sau | Dùng class cũ cho tới khi biên dịch lại | Biên dịch phục vụ mỗi lần khởi chạy |
| Kiểm soát đầu ra | Có **-d**, kiểm soát thư mục class | Không phải công cụ xuất artifact bằng **-d** |
| Kiểm tra lỗi | Có thể kiểm tra compile mà chưa chạy | Compile và run nằm trong một lần gọi; mã lỗi thì không chạy |
| Annotation processing | javac hỗ trợ cấu hình processor | Source-file mode vô hiệu annotation processing theo tài liệu launcher |
| Nhiều tệp nguồn | Hỗ trợ khai báo tường minh, source path, module source path và build tool | Java 17/21 chủ yếu cho một tệp nguồn được launch; các phiên bản mới hơn mở rộng phạm vi |
| Đóng gói và triển khai | Phù hợp JAR/module, pipeline build và CI | Hợp ví dụ nhỏ, script, thử nghiệm, học tập |
| Kiểm soát bytecode đích | Hỗ trợ **--release**, **--target** và các lựa chọn trình biên dịch | **--source** cho launcher chọn mức ngôn ngữ/API phù hợp; không thay thế toàn bộ tùy chọn javac |
| Phụ thuộc bên ngoài | Chỉ định lúc biên dịch và khi chạy | Có thể cung cấp classpath/module path phù hợp; cần hiểu giới hạn khám phá tệp nguồn theo bản JDK |

Chạy trực tiếp tệp nguồn **không có nghĩa bỏ qua compiler**, **không có nghĩa chạy mã Java như interpreter theo từng câu lệnh**, và **không bảo đảm chạy nhanh hơn**. Nó ưu tiên sự gọn nhẹ của một lần gọi lệnh; chi phí biên dịch vẫn phát sinh.

## 4. Quy tắc lệnh và cách truyền tham số

### 4.1. Đặt JVM/launcher option trước tên tệp nguồn

Ví dụ:

~~~bash
java -Xmx128m Hello.java Mai
~~~

**-Xmx128m** ở trước **Hello.java** là tùy chọn JVM; **Mai** ở sau tên tệp là tham số chương trình. Nếu viết:

~~~bash
java Hello.java -Xmx128m
~~~

thì chuỗi **-Xmx128m** được truyền vào **args[0]** của ứng dụng, không được hiểu là giới hạn heap của JVM.

Tương tự, khi chạy class đã biên dịch:

~~~bash
java -cp out Hello Mai
~~~

**-cp out** là tùy chọn launcher; **Hello** là tên lớp; **Mai** là tham số.

### 4.2. Kích hoạt source-file mode bằng cách nào?

Với bản JDK hỗ trợ, khi đối số ứng dụng đầu tiên chỉ đến **một tệp tồn tại có phần mở rộng .java**, launcher chọn source-file mode:

~~~bash
java Hello.java
~~~

Có thể dùng **--source** để chọn mức ngôn ngữ/API của lần biên dịch nguồn, ví dụ:

~~~bash
java --source 17 Hello.java Mai
~~~

Trên JDK hỗ trợ phiên bản nguồn 17, lệnh này chạy nguồn ở mức tương thích quy định bởi **--source 17**; khi dùng source launcher, tùy chọn này còn ảnh hưởng API nền tảng có thể dùng. Không nên coi **java --source 17** là cơ chế tạo tệp class tương thích cho môi trường Java 17: muốn tạo artifact dùng để triển khai, hãy dùng **javac --release 17**.

Đối với tệp nguồn không mang đuôi **.java**, **--source** cũng là tín hiệu cho launcher nhận diện source-file mode. Khi học cơ bản, ưu tiên **.java** vì rõ ràng và di động hơn.

### 4.3. Phân biệt những câu lệnh dễ nhầm

| Lệnh | Đúng nghĩa |
| --- | --- |
| **javac Hello.java** | Biên dịch, mặc định ghi Hello.class cạnh nguồn nếu không chỉ định -d |
| **javac -d out Hello.java** | Biên dịch và ghi class vào out |
| **java Hello** | Chạy class Hello đã có trên classpath phù hợp |
| **java -cp out Hello** | Chạy class Hello trong out |
| **java Hello.java** | Biên dịch nguồn để chạy ngay |
| **java --source 17 Hello.java** | Chạy source mode với mức ngôn ngữ/API nguồn tương ứng |
| **java -jar app.jar** | Chạy chương trình đóng gói JAR có điểm vào phù hợp |
| **java -m my.module/pkg.Main** | Chạy main class thuộc named module được resolve |

**Không thay tên lớp bằng tên tệp .class** trong lệnh khởi chạy tên lớp: sử dụng **java Hello**, không phải **java Hello.class**.

## 5. Khác biệt về file, classpath và tái sử dụng

### 5.1. javac xuất bytecode rõ ràng

Với tệp nguồn thuộc package:

~~~java
// src/demo/Greeter.java
package demo;

public final class Greeter {
    public static String message(String name) {
        return "Hello, " + name;
    }
}
~~~

Lệnh:

~~~bash
javac -d out src/demo/Greeter.java
~~~

tạo **out/demo/Greeter.class**. Java lưu class file theo cây package khi có thư mục output. Dùng **-d out** giúp tách nguồn và sản phẩm build. Lệnh biên dịch này chưa chạy chương trình và **Greeter** cũng không cần có **main** để trở thành một lớp thư viện hợp lệ.

Khi nhiều lớp cần dùng lẫn nhau, javac có thể biên dịch một nhóm nguồn và tìm mã phụ thuộc theo cấu hình source/classpath. Build tool như Maven hoặc Gradle còn quản lý incremental build, test, resource, dependency và đóng gói.

### 5.2. Source-file mode cần classpath khi dùng lớp đã biên dịch

Tạo thêm hai tệp với cấu trúc:

~~~text
work/
├── Main.java
└── src/
    └── demo/
        └── Greeter.java
~~~

Nội dung **src/demo/Greeter.java** như phần 5.1. Nội dung **Main.java**:

~~~java
import demo.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message("Mai"));
    }
}
~~~

Biên dịch lớp thư viện trước:

~~~bash
javac -d out src/demo/Greeter.java
~~~

Sau đó có thể chọn một trong hai cách:

~~~bash
# Cách A: biên dịch cả chương trình rồi chạy class
javac -cp out -d out Main.java
java -cp out Main
~~~

~~~bash
# Cách B: chỉ chạy Main.java ở source-file mode
java -cp out Main.java
~~~

Cả hai cách có stdout:

~~~text
Hello, Mai
~~~

Ví dụ chứng minh source-file mode **không bị cấm dùng thư viện**: lớp phụ thuộc **demo.Greeter** đã có trong classpath **out**; source launcher biên dịch **Main.java** để chạy và nạp **Greeter.class**. Trên Windows, một classpath gồm nhiều mục thường ngăn bằng **;**; trên Linux/macOS là **:**. Lệnh trên chỉ có một mục nên chạy được ở các hệ điều hành.

**Giới hạn quan trọng của Java 17/21:** source-file mode không tự quét và biên dịch mọi tệp **.java** trong dự án. Nếu bỏ bước biên dịch **Greeter.java** rồi gọi **java Main.java**, không thể mặc định kỳ vọng launcher tìm tệp nguồn **src/demo/Greeter.java** như Gradle hoặc javac được cấu hình sourcepath. Java 25 có mở rộng đáng kể về việc tìm source phụ thuộc; xem phần 8.

### 5.3. Khi cần tái sử dụng cho CI/CD và phân phối

Với chương trình đủ lớn, quy trình chuẩn thường là:

~~~text
source code
   |
   v
javac hoặc build tool --> thư mục class / JAR / modular artifact
   |
   +--> chạy test, kiểm tra bytecode, đóng gói
   |
   v
java -cp ... Main     hoặc     java -jar app.jar     hoặc     java -m ...
~~~

Source-file mode không có bước tạo artifact phân phối tương đương. Mục đích của nó là rút ngắn vòng thử nghiệm, bài ví dụ và các tiện ích nhỏ. Với release build, cần class/JAR được xây dựng và kiểm chứng rõ ràng.

## 6. Kiểm tra tương thích phiên bản: --release và --source

Giả sử máy phát triển cài JDK 21 nhưng ứng dụng phải chạy trên Java 17. Hãy biên dịch artifact theo phiên bản đích:

~~~bash
javac --release 17 -d out Hello.java
java -cp out Hello Mai
~~~

**--release 17** của **javac** kiểm soát cú pháp, API Java chuẩn khả dụng và định dạng class file phù hợp với Java 17. Đây là lựa chọn phổ biến khi build cho JDK cũ hơn. Không nên chỉ dùng **-source 17** rồi giả định class file đã tương thích Java 17, vì **-source** một mình không bảo đảm toàn bộ mục tiêu đó.

Lệnh source launcher:

~~~bash
java --source 17 Hello.java Mai
~~~

khác về mục đích: nó **biên dịch và chạy ngay trên JVM đang dùng**, không xuất một bộ class file để mang sang JVM 17. Nếu máy hiện tại là JDK 21, quá trình chạy vẫn diễn ra trên JDK 21. Muốn kiểm tra thực tế trên Java 17, cần chạy bằng chính runtime Java 17 (hoặc CI image tương ứng).

**Lưu ý:** JDK chỉ hỗ trợ một số phiên bản nguồn cũ nhất định. Trước khi dùng **--release N** hay **--source N**, hãy kiểm tra JDK hiện tại bằng **javac --help**, **java --help**, **javac -version**, **java -version**.

## 7. Lỗi biên dịch, thứ tự lớp và giới hạn riêng của source-file mode

### 7.1. Lỗi biên dịch xuất hiện trước khi chương trình chạy

Nếu đổi trong **Hello.java**:

~~~java
System.out.println(unknownName);
~~~

mà không khai báo biến **unknownName**, cả **javac Hello.java** lẫn **java Hello.java** đều phát hiện lỗi biên dịch. Với quy trình javac, lỗi xuất hiện ở bước biên dịch; với source launcher, lỗi xuất hiện trong lệnh khởi chạy nên main không được thực thi. Thông báo chi tiết và số dòng phụ thuộc tệp/JDK; không nên giả định một câu stderr cố định.

### 7.2. Tên tệp và thứ tự top-level class trong Java 17/21

Với **javac**, quy tắc thông thường là một **public top-level class** phải nằm trong tệp trùng tên (**public class Hello** trong **Hello.java**). Với source launcher Java 17/21, ví dụ:

~~~java
// StartHere.java
class Entry {
    public static void main(String[] args) {
        System.out.println("Entry chạy");
    }
}

class Helper {
    static int value() {
        return 42;
    }
}
~~~

chạy được bằng:

~~~bash
java StartHere.java
~~~

stdout:

~~~text
Entry chạy
~~~

Trong Java 17/21, source-file launcher chọn **top-level class đầu tiên** trong tệp làm class chạy; class đó phải chứa phương thức **public static void main(String[] args)** hợp lệ. Các top-level class còn lại trong cùng tệp có thể được dùng làm trợ giúp. Tên tệp **StartHere.java** không bắt buộc giống tên top-level class **Entry** trong ví dụ này vì **Entry không public**. Khi chuyển sang build javac thường, vẫn nên dùng tên tệp và bố cục lớp chuẩn để tránh nhầm.

Thứ tự có ý nghĩa: đổi chỗ **Helper** lên trước **Entry** ở nguồn Java 17/21 sẽ làm launcher tìm main ở lớp đầu tiên và không khởi chạy được vì Helper không có main, dù Entry ở phía sau. Đừng dựa vào việc launcher tùy ý tìm lớp có main trong cả tệp.

### 7.3. Annotation processor và các tùy chọn javac

**javac** hỗ trợ điều khiển quá trình biên dịch với các tùy chọn như:

~~~bash
javac -d out -Xlint:all Hello.java
~~~

Nếu có annotation processor thì javac có thể cấu hình processor path, processor và các vòng xử lý annotation. Ngược lại, source-file mode **vô hiệu annotation processing**; không có cơ chế truyền đầy đủ mọi option javac qua lệnh **java Hello.java**. Những dự án phụ thuộc code generation hoặc compile-time processing như nhiều cấu hình Lombok/MapStruct nên dùng build javac/Gradle/Maven phù hợp thay vì kỳ vọng source launcher tự tạo mã.

**java Hello.java** cũng không thay thế **javac -d out**, **javac -h ...** hay bước đóng gói JAR.

### 7.4. Package, module và classpath

- Source launcher Java 17/21 biên dịch tệp nguồn trong **unnamed module**, dù lớp trong nguồn có thể khai báo một **package** bình thường. Điều này khác với việc tạo một explicit named module bằng **module-info.java** và biên dịch bằng module source path.
- **javac** có thể biên dịch module theo **--module-source-path**, và ứng dụng module có thể chạy với **java --module-path ... -m module/class**.
- Đừng giả định chỉ vì chạy file .java là các quy tắc JPMS, exports và requires của cả dự án sẽ được áp dụng giống một modular build đầy đủ.
- Có thể dùng **-cp / --class-path** hoặc các tùy chọn module path được launcher hỗ trợ cho phụ thuộc thích hợp, nhưng vẫn phải phân biệt **mã nguồn cần biên dịch** và **class/JAR đã biên dịch**.

## 8. Sự khác nhau theo phiên bản JDK

Bài này dùng cú pháp chuẩn Java 17+; tuy nhiên **khả năng của source launcher đã thay đổi theo bản JDK**. Vì vậy khi học “chạy tệp nguồn trực tiếp”, cần ghi rõ JDK đang dùng.

| Phiên bản | Điểm cần nhớ |
| --- | --- |
| Java 8 và trước | Không có source-file mode qua lệnh **java File.java** như ví dụ; dùng javac rồi java |
| Java 11 | JEP 330 giới thiệu chạy một tệp nguồn bằng java |
| Java 17/21 | Mô hình single-file source launcher: biên dịch tệp nguồn được chỉ định, không tự biên dịch mọi tệp nguồn phụ thuộc trong source tree |
| Java 25+ | JEP 458 mở rộng source launcher: có thể tìm và biên dịch các tệp .java cần thiết trong cùng source tree; hỗ trợ sử dụng module-info.java trong cây nguồn theo quy tắc phiên bản này |

Ví dụ có hai tệp ở phần 5 được thiết kế để chạy chắc chắn trên Java 17/21 bằng cách biên dịch **Greeter.class** trước. Trên JDK 25+, source launcher có thể biên dịch mã nguồn phụ thuộc khi source tree được bố trí phù hợp; điều đó **không biến java File.java thành một build system đầy đủ**, không xuất artifact .class để tái sử dụng và không bật annotation processing. Khi viết tài liệu hoặc CI, nên ghi rõ **minimum JDK version** thay vì dựa ngầm vào tính năng của bản JDK mới nhất.

Ngoài ra, các thay đổi ngôn ngữ ở Java mới (ví dụ entry point hoặc cách viết chương trình ngắn hơn) là một vấn đề khác với **cơ chế nguồn được biên dịch và chạy**. Để so sánh công bằng trên Java 17, các ví dụ trong bài sử dụng **public static void main(String[] args)** truyền thống.

## 9. Khi nào chọn cách nào?

**Dùng javac (thường thông qua Gradle/Maven) khi:**

- Có nhiều package, nhiều module, dependency, resource hoặc mã tự sinh.
- Cần kiểm thử riêng bước compile, chạy kiểm thử unit/integration, lint hay annotation processing.
- Phải đóng gói ứng dụng/thư viện thành artifact ổn định cho CI/CD hoặc triển khai.
- Cần build cho phiên bản Java khác, dùng **--release**, hoặc kiểm soát compiler options.
- Muốn tái sử dụng class file đã build trong nhiều lần chạy mà không compile lại.

**Dùng java File.java khi:**

- Đang học Java, muốn chạy ví dụ tự chứa chỉ với một lệnh.
- Viết script/tiện ích nhỏ trên máy đã cài JDK tương thích.
- Cần thí nghiệm nhanh với mã nguồn mà chưa cần tạo JAR/class output.
- Có phụ thuộc đã biên dịch và biết cách truyền classpath phù hợp.

Không có quy tắc “javac nhanh hơn trong mọi hoàn cảnh”: source launcher tiết kiệm thao tác, trong khi build trước có thể tránh lặp compile cho các lần chạy tiếp theo. Hiệu năng thực tế còn phụ thuộc độ lớn nguồn, dependency, JVM warm-up và cách đo. Để đánh giá tốc độ chương trình sau khi khởi động, phải tách **thời gian compile/startup** khỏi **thời gian thực thi logic**.

## 10. Một vài tình huống và cách suy luận

**Tình huống A:** Người học thay một dòng trong **Hello.java**, chạy **java -cp out Hello** và vẫn thấy đầu ra cũ.

**Nguyên nhân:** đang chạy **Hello.class** cũ. Cần chạy lại **javac -d out Hello.java** hoặc dùng **java Hello.java** để thử nội dung nguồn mới.

**Tình huống B:** **java Hello** báo không tìm thấy main class, nhưng **java Hello.java** chạy được.

**Nguyên nhân thường gặp:** lớp **Hello** chưa được biên dịch hoặc không nằm trong classpath mà launcher tìm. Java source launcher có thể biên dịch từ tệp gốc mà không cần class tồn tại trước.

**Tình huống C:** **javac Main.java** thất bại vì thiếu một thư viện, nhưng người học nghĩ **java Main.java** sẽ tự tải dependency.

**Giải thích:** hai lệnh đều cần truy cập dependency. Source launcher không tự tải mọi JAR từ Maven Central và không thay thế Gradle/Maven. Cần cung cấp classpath/module path hoặc sử dụng build tool.

**Tình huống D:** Project sử dụng annotation processor sinh mã trong compile time.

**Hướng xử lý:** dùng javac hoặc build tool có cấu hình annotation processor. Source-file mode không chạy annotation processing.

**Tình huống E:** Phải gửi một JAR chạy trên Java 17, nhưng máy lập trình dùng JDK 21.

**Hướng xử lý:** dùng build chuẩn với **javac --release 17** (hoặc cấu hình Gradle/Maven tương ứng), kiểm thử trên runtime 17 và đóng gói. **java --source 17 File.java** không phải bước phát hành artifact.

## 11. Bài tập thực hành ngắn

1. Tạo **Hello.java** ở phần 2. Chạy **java Hello.java A** và ghi stdout.
2. Chạy **javac -d out Hello.java** rồi **java -cp out Hello B**; kiểm tra tệp **out/Hello.class** đã được tạo.
3. Đổi nội dung in ra trong nguồn, **không biên dịch lại**, chạy **java -cp out Hello B** rồi **java Hello.java B**; giải thích vì sao đầu ra khác nhau.
4. Thử **java -Xmx128m Hello.java A** và **java Hello.java -Xmx128m**; quan sát **args[0]**.
5. Tạo **Greeter.java** và **Main.java** như phần 5; biên dịch helper và so sánh hai cách khởi chạy main.
6. Nếu đang dùng JDK 25+, thử bố trí mã nguồn phụ thuộc theo hướng dẫn source tree của phiên bản đó và so sánh với giới hạn Java 17/21.

**Câu hỏi tự kiểm tra:**

- Vì sao **java Hello.java** không tạo sản phẩm build tương đương với **javac -d out Hello.java**?
- Lệnh **java Hello.java** có “bỏ qua biên dịch” không?
- **-cp out** tác động thế nào khi chạy class so với khi source launcher cần dùng một thư viện đã biên dịch?
- Tại sao **java -cp out Hello** có thể chạy mã cũ sau khi sửa **Hello.java**?
- Khi nào phải dùng **javac --release 17**, và tại sao **java --source 17** không thay thế nó?
- Những giới hạn nào của single-file source launcher Java 17/21 đã được mở rộng trong JDK mới?

## 12. Tài liệu gốc để tra cứu

- **Oracle Java 17 – The java Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle Java 21 – The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle Java 21 – The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java 25 – The java Command:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **OpenJDK JEP 330 – Launch Single-File Source-Code Programs:** https://openjdk.org/jeps/330
- **OpenJDK JEP 458 – Launch Multi-File Source-Code Programs:** https://openjdk.org/jeps/458

**Ghi nhớ:** **javac** tạo class file để kiểm soát build và tái sử dụng; **java File.java** tự biên dịch nguồn khi khởi chạy để tiện thử và chạy mã trực tiếp. Cả hai cuối cùng đều chạy bytecode trên JVM, nhưng cần chọn theo **quy mô dự án, yêu cầu build, dependency và phiên bản JDK**.