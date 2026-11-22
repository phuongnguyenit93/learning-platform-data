# Giới hạn kiểm tra thay đổi của javac và vai trò của depend

Apache Ant hỗ trợ biên dịch Java theo kiểu incremental. Khi chạy lại build, task **javac** có thể bỏ qua những tệp nguồn mà Ant cho rằng không cần biên dịch lại. Cách kiểm tra mặc định này nhanh và phù hợp với nhiều dự án, nhưng chủ yếu dựa trên sự tồn tại và dấu thời gian của các cặp tệp nguồn và tệp class tương ứng.

Giới hạn xuất hiện khi một lớp cần biên dịch lại vì lớp khác mà nó phụ thuộc đã thay đổi, dù source của lớp đó không mới hơn class file tương ứng. Task **depend** của Ant xử lý một phần vấn đề này bằng cách phân tích quan hệ giữa các class file, sau đó xóa những class file bị ảnh hưởng để javac biên dịch lại chúng.

Cần phân biệt ba khái niệm:

- **javac mặc định** chọn source cần biên dịch dựa trên tên tệp và timestamp.
- **Task depend** phân tích class dependency và xóa class file phụ thuộc vào class đã lỗi thời.
- **Thuộc tính depend="true" của javac** là tùy chọn riêng cho một số compiler cũ như Jikes và classic. Nó không phải task depend và không bật cơ chế phân tích dependency của Ant cho compiler javac hiện đại.

## 1. Cách javac quyết định tệp nào cần biên dịch

Khi task javac được thực thi, Ant quét cây thư mục nguồn và thư mục đích. Với mỗi tệp Java, Ant tìm class file tương ứng. Một source được đưa vào danh sách biên dịch nếu:

- Chưa có class file tương ứng.
- Class file tương ứng cũ hơn source.

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"/>
~~~

Giả sử dự án có:

~~~text
src/main/java/
└── com/example/
    ├── App.java
    ├── Service.java
    └── Model.java

build/classes/
└── com/example/
    ├── App.class
    ├── Service.class
    └── Model.class
~~~

Nếu **Service.java** mới hơn **Service.class**, Ant đưa **Service.java** vào lần biên dịch. Nếu class file của App và Model vẫn mới hơn hoặc bằng source tương ứng, Ant có thể bỏ qua hai source đó.

| Source | Class tương ứng | Quyết định theo timestamp |
|---|---|---|
| **App.java** | Không có App.class | Biên dịch |
| **Service.java** | Service.class cũ hơn | Biên dịch |
| **Model.java** | Model.class mới hơn | Bỏ qua |

Đây là kiểm tra dựa trên thời gian sửa đổi, không phải so sánh nội dung byte của source và class. Ant không đọc toàn bộ mã Java để suy luận mọi lớp bị ảnh hưởng.

## 2. Giới hạn: javac không tự phân tích toàn bộ quan hệ phụ thuộc

Cách chọn source mặc định của Ant chủ yếu dựa trên tên source/class và timestamp. Nó không quét mã nguồn để xây dựng đồ thị quan hệ giữa các lớp. Vì vậy, có thể xuất hiện tình huống một class cần biên dịch lại nhưng cặp source/class của chính nó không cho thấy điều đó.

Ví dụ:

~~~java
// Model.java
package com.example;

public class Model {
    public String getCode() {
        return "A";
    }
}
~~~

~~~java
// Service.java
package com.example;

public class Service {
    public String describe(Model model) {
        return model.getCode();
    }
}
~~~

~~~java
// App.java
package com.example;

public class App {
    public static void main(String[] args) {
        Model model = new Model();
        System.out.println(new Service().describe(model));
    }
}
~~~

Quan hệ phụ thuộc:

~~~text
App ───────► Service
 │              │
 └────────────► Model
                ▲
                │
             Service
~~~

Giả sử Model.java thay đổi chữ ký phương thức getCode() hoặc một kiểu dữ liệu công khai. Model.java mới hơn Model.class, nên Ant nhận ra cần biên dịch Model.java.

Nhưng Service.java và App.java có thể không thay đổi. Nếu class file tương ứng của chúng vẫn mới hơn source, bộ quét timestamp của Ant không nhất thiết đưa chúng vào danh sách biên dịch, dù bytecode của chúng có thể không còn tương thích với class Model mới.

Hai loại kiểm tra trả lời hai câu hỏi khác nhau:

- **Kiểm tra timestamp:** Source này có mới hơn class tương ứng không?
- **Kiểm tra dependency:** Class nào tham chiếu tới class đã thay đổi và vì vậy có thể cần biên dịch lại?

## 3. Những trường hợp javac mặc định có thể bỏ sót

### Thay đổi API của lớp được sử dụng bởi lớp khác

Nếu một lớp thay đổi phương thức, kiểu trả về, constructor hoặc thành viên được lớp khác sử dụng, các lớp tiêu thụ có thể cần biên dịch lại. Tuy nhiên, source của chúng có thể không mới hơn class tương ứng.

Ví dụ, Model đổi từ:

~~~java
public String getCode()
~~~

thành:

~~~java
public int getCode()
~~~

Service.java vẫn gọi model.getCode() như trước. Source của Service không thay đổi, nhưng nó cần được biên dịch lại để kiểm tra và tạo bytecode phù hợp với API mới. Kiểm tra timestamp đơn thuần không suy ra được quan hệ này.

### Lớp lồng nhau và tên class khác tên source

Một tệp source có thể tạo ra nhiều class file:

~~~java
public class Report {
    static class Row {
    }
}
~~~

Compiler có thể tạo Report.class và Report$Row.class. Cách kiểm tra mặc định của Ant dựa vào tên source/class tương ứng, không phân tích source để hiểu mọi lớp lồng nhau hoặc lớp có tên khác với tệp source.

Nếu một class file phụ được tạo ra bị xóa hoặc lỗi thời trong khi class file tương ứng với tên source vẫn còn mới, kiểm tra tên/timestamp cơ bản có thể không nhận ra toàn bộ trạng thái cần xây dựng lại.

### Thay đổi lớp phụ thuộc trong thư viện dự án

Nếu một lớp trong dự án phụ thuộc vào một JAR nội bộ được cập nhật, source của lớp tiêu thụ không đổi. Ant không tự suy luận mọi class file nào cần biên dịch lại chỉ từ việc JAR mới hơn.

Task depend có thể kiểm tra thêm dependency đối với class hoặc JAR được khai báo trong classpath của nó.

### Tệp được tạo hoặc thay đổi ngoài quy tắc timestamp thông thường

Một số đầu ra như native header, resource được sinh bởi công cụ khác hoặc tệp class được tạo bởi quy trình riêng có thể không được phản ánh đầy đủ trong cặp Java source/class mà Ant đang dùng để chọn source.

Với native header được tạo qua thuộc tính **nativeheaderdir**, tài liệu javac lưu ý logic chọn source không tính đến timestamp của native header. Nếu class mới hơn source nhưng native header cần cập nhật, task có thể không biên dịch lại source chỉ vì header đã cũ.

## 4. Task depend làm gì?

Task **depend** bổ sung bước phân tích dependency giữa các class file. Nó hoạt động theo trình tự khái quát:

1. Xác định class nào đã lỗi thời so với source tương ứng bằng cơ chế timestamp.
2. Đọc class file để lấy các tham chiếu tới class khác đã được compiler ghi vào bytecode.
3. Xác định những class phụ thuộc vào class đã lỗi thời.
4. Xóa class file của các lớp bị ảnh hưởng khỏi thư mục đích.
5. Khi javac chạy sau đó, các source có class file bị xóa được xem là chưa có đầu ra và được biên dịch lại.

Task depend **không biên dịch Java source**. Nó chỉ phân tích quan hệ class và xóa class file cần được tạo lại. Vì vậy, nó thường được đặt trước task javac trong target compile.

Ví dụ luồng xử lý:

~~~text
Model.java mới hơn Model.class
             │
             ▼
       depend kiểm tra
             │
             ▼
  Phát hiện Service.class phụ thuộc Model
             │
             ▼
       Xóa Service.class
             │
             ▼
        javac chạy
             │
       ┌─────┴─────┐
       ▼           ▼
  Biên dịch     Biên dịch
  Model.java   Service.java
~~~

Lớp bị thay đổi và những lớp phụ thuộc được đưa trở lại danh sách biên dịch thông qua việc class file tương ứng không còn tồn tại.

## 5. Cấu hình task depend cơ bản

Một cấu hình thường gặp:

~~~xml
<depend srcdir="src/main/java"
        destdir="build/classes"
        cache="build/depend-cache"
        closure="false"/>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"/>
~~~

Các thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| **srcdir** | Thư mục gốc chứa Java source cần xét |
| **destdir** | Thư mục gốc chứa class file đã biên dịch |
| **cache** | Thư mục lưu thông tin dependency để tái sử dụng giữa các lượt build |
| **closure** | Có xét cả quan hệ phụ thuộc gián tiếp hay chỉ quan hệ trực tiếp |
| **classpath** | Class/JAR bổ sung để kiểm tra dependency với các thư viện được khai báo |
| **dump** | Ghi thông tin dependency ở mức log debug |
| **warnOnRmiStubs** | Điều khiển cảnh báo đối với các tệp có vẻ là RMI stub/skeleton nhưng không có source tương ứng |

Nếu có nhiều source root, srcdir có thể nhận một Path gồm nhiều thư mục. Có thể dùng include/exclude để giới hạn source cần xét:

~~~xml
<depend srcdir="src/main/java"
        destdir="build/classes"
        cache="build/depend-cache">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</depend>
~~~

Phạm vi source được xét bởi depend nên tương ứng với phạm vi mà javac sẽ biên dịch. Nếu hai task dùng tập source khác nhau, một class có thể bị xóa nhưng source tương ứng lại bị loại khỏi javac, hoặc một dependency cần thiết không được kiểm tra.

## 6. Vai trò của closure

Thuộc tính **closure** quyết định depend chỉ xóa các class phụ thuộc trực tiếp hay tiếp tục theo quan hệ phụ thuộc bắc cầu.

Giả sử:

~~~text
A phụ thuộc B
B phụ thuộc C
~~~

Khi source của C lỗi thời:

- **closure="false"**: depend xóa class trực tiếp phụ thuộc vào C, tức B.class.
- **closure="true"**: depend tiếp tục xét quan hệ bắc cầu và xóa cả B.class lẫn A.class.

Sơ đồ:

~~~mermaid
flowchart LR
    A["A.class"] --> B["B.class"]
    B --> C["C.class"]
    C --> D["C.java thay đổi"]
~~~

Với closure false, chỉ lớp ở cạnh trực tiếp của C bị vô hiệu hóa. Với closure true, Ant đi ngược toàn bộ chuỗi phụ thuộc liên quan để xóa các class bị ảnh hưởng gián tiếp.

Cấu hình:

~~~xml
<depend srcdir="src"
        destdir="build/classes"
        cache="build/depend-cache"
        closure="true"/>
~~~

Mặc định của closure là false. Bật closure có thể làm nhiều class file bị xóa hơn, kéo theo nhiều source được javac biên dịch lại. Điều này tăng độ bao phủ của việc vô hiệu hóa nhưng cũng có thể làm build tốn thời gian hơn.

Trong nhiều dự án, các quan hệ trực tiếp là đủ vì lớp phụ thuộc thường có tham chiếu trực tiếp tới kiểu mà nó sử dụng. Chọn true khi cần theo toàn bộ chuỗi phụ thuộc gián tiếp và chấp nhận số lượng biên dịch lại tăng lên.

## 7. Kiểm tra dependency với JAR hoặc class bên ngoài

Task depend có thể nhận **classpath** để xét các class/JAR mà mã nguồn dự án phụ thuộc. Đây là trường hợp hữu ích khi dự án có thư viện nội bộ được build ở một bước khác.

Ví dụ, ứng dụng dùng một JAR API nội bộ:

~~~xml
<path id="project.api.path">
    <pathelement location="lib/company-api.jar"/>
</path>

<depend srcdir="src/main/java"
        destdir="build/classes"
        cache="build/depend-cache">
    <classpath refid="project.api.path"/>
</depend>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="project.api.path"/>
</javac>
~~~

Nếu company-api.jar được cập nhật, depend có thể phát hiện class file của ứng dụng phụ thuộc vào phần tử classpath đã cũ và xóa các class file liên quan để javac biên dịch lại.

Classpath dành cho depend không nhất thiết phải giống hoàn toàn classpath biên dịch. Nên đưa vào những thư viện có khả năng thay đổi mà dự án cần theo dõi, chẳng hạn JAR do chính nhóm build. Không cần đưa các thư viện ổn định như JDK runtime hoặc mọi JAR bên thứ ba không dự kiến thay đổi, vì điều đó làm tăng thời gian phân tích mà không đem lại lợi ích tương ứng.

## 8. Đặt depend trước javac trong quy trình build

Một target compile có thể tổ chức như sau:

~~~xml
<project name="inventory" default="compile" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="depend.cache" location="${build.dir}/depend-cache"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile" depends="prepare"
            description="Kiểm tra dependency và biên dịch Java">

        <depend srcdir="${src.dir}"
                destdir="${classes.dir}"
                cache="${depend.cache}"
                closure="true">
            <include name="**/*.java"/>
            <exclude name="**/generated/**"/>
        </depend>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false">
            <include name="**/*.java"/>
            <exclude name="**/generated/**"/>
        </javac>

    </target>

</project>
~~~

Thứ tự có ý nghĩa:

1. **prepare** tạo thư mục class.
2. **depend** kiểm tra source/class và quan hệ giữa các class, xóa những class file bị ảnh hưởng.
3. **javac** quét source và biên dịch những tệp chưa có class hoặc class cũ hơn source.
4. Những class file bị depend xóa sẽ khiến source tương ứng được đưa vào lần biên dịch.

Điều quan trọng là giữ phạm vi include/exclude nhất quán giữa depend và javac. Nếu depend theo dõi một tập source khác với javac, kết quả vô hiệu hóa có thể không phản ánh đúng tập source được biên dịch.

### Khi dùng target riêng cho dependency

Có thể tách thành hai target để dễ đọc:

~~~xml
<target name="check-dependencies">
    <depend srcdir="${src.dir}"
            destdir="${classes.dir}"
            cache="${depend.cache}"
            closure="true"/>
</target>

<target name="compile" depends="prepare,check-dependencies"
        description="Biên dịch source sau khi xử lý dependency">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"/>
</target>
~~~

Cách này phù hợp khi các bước build cần tái sử dụng bước kiểm tra dependency. Tuy nhiên, hãy bảo đảm prepare chạy trước check-dependencies nếu depend cần thư mục đích tồn tại, và giữ thứ tự target rõ ràng qua thuộc tính depends.

## 9. Phân biệt task depend với thuộc tính depend của javac

Hai cấu hình có tên gần giống nhau nhưng vai trò khác nhau.

### Task depend

~~~xml
<depend srcdir="src"
        destdir="build/classes"
        cache="build/depend-cache"/>
~~~

Đây là task riêng của Ant. Nó phân tích class file để xác định lớp nào phụ thuộc vào class đã lỗi thời, rồi xóa class file của lớp bị ảnh hưởng. Task này thường được đặt trước javac.

### Thuộc tính depend="true" trên javac

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       depend="true"/>
~~~

Thuộc tính này yêu cầu bật dependency tracking ở những compiler có hỗ trợ. Theo tài liệu Ant, các compiler được hỗ trợ là **Jikes** và **classic**. Nó không bật task depend và không cung cấp cơ chế phân tích dependency của Ant cho compiler **modern/javac** hiện đại.

Với compiler hiện đại, không nên dựa vào:

~~~xml
<javac depend="true"/>
~~~

để giải quyết khoảng trống dependency của cơ chế timestamp. Nếu cần bước phân tích class dependency của Ant, hãy cấu hình task depend riêng trước javac.

| Tiêu chí | Task depend | Thuộc tính javac depend="true" |
|---|---|---|
| Hình thức | Task độc lập | Thuộc tính của task javac |
| Cách hoạt động | Phân tích class file và xóa class bị ảnh hưởng | Bật tùy chọn dependency tracking của compiler |
| Compiler | Cơ chế của Ant | Chỉ compiler hỗ trợ như Jikes và classic |
| Vị trí trong build | Trước javac | Nằm trong khai báo javac |
| Dùng với modern javac | Có thể dùng như task riêng nếu task có sẵn | Không phải cơ chế dependency tracking của modern javac |

## 10. Giới hạn của chính task depend

Task depend mở rộng việc kiểm tra nhưng không thể phát hiện mọi quan hệ source. Nó phân tích class file, không phân tích mã nguồn Java. Do đó, kết quả phụ thuộc vào các tham chiếu mà compiler đã ghi vào bytecode.

Một số trường hợp có thể không được phát hiện:

- Compiler tối ưu và loại bỏ một quan hệ class khỏi bytecode dù source ban đầu có quan hệ đó.
- Lớp không public gây khó khăn trong việc liên kết class file với source file. Task depend không thể luôn xác định class file tương ứng với source.
- Thay đổi một hằng primitive compile-time được khai báo trong class khác có thể không làm class tiêu thụ được nhận diện là phụ thuộc, vì giá trị hằng có thể đã được nhúng trực tiếp vào bytecode của lớp sử dụng.
- Các lớp không public bị thiếu có thể không được task depend hoặc compiler task phát hiện đầy đủ.
- Dependency ngoài phạm vi source, destdir và classpath được cấu hình sẽ không được kiểm tra.

Ví dụ về hằng compile-time:

~~~java
public final class BuildFlags {
    public static final boolean DEBUG = false;
}
~~~

Một lớp khác sử dụng **BuildFlags.DEBUG** có thể được compiler nhúng giá trị false trực tiếp vào bytecode. Nếu giá trị trong BuildFlags đổi thành true, class file của lớp sử dụng không nhất thiết chứa tham chiếu tới BuildFlags để depend phát hiện và xóa nó. Vì vậy, lớp tiêu thụ có thể cần biên dịch lại dù task depend không nhận ra quan hệ này.

Với những trường hợp như vậy, có thể cần clean build, biên dịch lại toàn bộ module hoặc thiết kế quy trình build rõ ràng hơn khi thay đổi API/hằng số.

## 11. Hiệu năng và lựa chọn chiến lược

Task depend phải đọc class file và xây dựng thông tin quan hệ. Chi phí phụ thuộc vào số class, độ phức tạp của đồ thị và số class bị lỗi thời.

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| Chỉ dùng javac timestamp | Đơn giản, nhanh, ít cấu hình | Có thể bỏ sót class tiêu thụ cần biên dịch lại khi dependency thay đổi |
| depend rồi javac | Xử lý được nhiều thay đổi class dependency hơn | Thêm thời gian phân tích và có thể xóa nhiều class |
| Clean rồi javac | Kết quả build mới từ đầu, tránh class cũ còn sót | Tốn thời gian biên dịch toàn bộ |
| Công cụ build có đồ thị dependency riêng | Có thể mô hình hóa đầu vào/đầu ra và quan hệ module rõ hơn | Cần cấu hình hoặc công cụ khác; không tự động thay thế mọi giới hạn của compiler |

Với dự án nhỏ, clean build có thể đơn giản và đáng tin cậy hơn việc duy trì cache dependency. Với dự án lớn có thời gian biên dịch đáng kể, depend có thể giảm rủi ro class tiêu thụ còn cũ trong incremental build. Nên đo thời gian thực tế trước khi bật closure hoặc đưa nhiều thư viện vào classpath của depend.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Sửa API một class nhưng class sử dụng không được biên dịch lại | javac chỉ thấy source tiêu thụ không mới hơn class tương ứng | Chạy depend trước javac |
| depend không xóa class mong đợi | Dependency không có trong bytecode hoặc source/destdir không khớp cấu trúc package | Kiểm tra cấu trúc source/class và giới hạn của bytecode analysis |
| javac biên dịch lại quá nhiều class | Bật closure true hoặc classpath có nhiều phần tử thay đổi | Xem lại closure và thu hẹp classpath theo dõi |
| depend không thấy thay đổi trong JAR nội bộ | JAR chưa được khai báo trong classpath của depend | Thêm JAR dự án vào nested classpath |
| javac depend true không có tác dụng | Compiler đang dùng không hỗ trợ thuộc tính này | Dùng task depend độc lập với modern javac |
| Class file bị xóa nhưng source không được biên dịch | Include/exclude của depend và javac không đồng nhất | Đồng bộ phạm vi source giữa hai task |
| Thay đổi hằng số nhưng lớp tiêu thụ vẫn dùng giá trị cũ | Compiler đã inline hằng vào bytecode, dependency không còn thể hiện | Clean hoặc biên dịch lại các lớp tiêu thụ |
| Build chậm sau khi bật depend | Phân tích graph tốn chi phí hoặc closure làm xóa nhiều class | Đo hiệu năng, điều chỉnh closure/cache và phạm vi theo dõi |

## 13. Nguyên tắc sử dụng

- Hiểu rằng javac mặc định chọn source theo sự tồn tại và timestamp của class file tương ứng.
- Đặt source root ở thư mục gốc package; dùng include/exclude để lọc package thay vì cắt mất một phần cấu trúc package khỏi srcdir.
- Dùng task depend khi cần phát hiện và vô hiệu hóa class tiêu thụ bị ảnh hưởng bởi class đã lỗi thời.
- Đặt depend trước javac để các class file bị xóa được biên dịch lại trong cùng lượt build.
- Giữ phạm vi source của depend và javac nhất quán.
- Chỉ khai báo classpath của depend cho những class/JAR có khả năng thay đổi và cần được theo dõi.
- Chọn closure theo mức độ bao phủ mong muốn và chi phí biên dịch lại.
- Không nhầm task depend với thuộc tính depend="true" của javac; thuộc tính đó chỉ dành cho Jikes và classic.
- Dùng clean build khi thay đổi có thể nằm ngoài khả năng phát hiện của timestamp hoặc bytecode dependency analysis, đặc biệt với compile-time constants.

Javac incremental giúp tránh biên dịch lại source không thay đổi, nhưng timestamp không mô tả đầy đủ quan hệ giữa các lớp. Task depend bổ sung bước phân tích class dependency, xóa các class file bị ảnh hưởng để javac tạo lại chúng. Khi hiểu đúng giới hạn của cả hai cơ chế, build Ant có thể cân bằng giữa tốc độ incremental và độ tin cậy của kết quả biên dịch.

## Tài liệu tham khảo

- [Apache Ant — Javac Task](https://ant.apache.org/manual/Tasks/javac.html)
- [Apache Ant — Depend Task](https://ant.apache.org/manual/Tasks/depend.html)
- [Apache Ant — Overview of Tasks](https://ant.apache.org/manual/tasksoverview.html)

