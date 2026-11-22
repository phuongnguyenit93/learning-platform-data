# Giới hạn khi nguồn bị xóa, dependency thay đổi hoặc cấu hình đổi

Build tăng dần (incremental build) giúp Apache Ant tránh lặp lại những công việc không cần thiết. Với Java, task **javac** thường chỉ biên dịch source chưa có class file tương ứng hoặc source mới hơn class file. Với tài nguyên, task copy có thể bỏ qua tệp đích đã mới hơn nguồn. Cách làm này tiết kiệm thời gian, nhưng timestamp của từng tệp không mô tả toàn bộ trạng thái của một dự án.

Ba thay đổi đặc biệt dễ làm đầu ra tăng dần bị cũ:

1. **Nguồn bị xóa hoặc đổi tên**: đầu ra cũ có thể vẫn còn dù source đã biến mất.
2. **Dependency thay đổi**: lớp tiêu thụ có thể cần biên dịch lại dù source của nó không thay đổi.
3. **Cấu hình build thay đổi**: compiler option, classpath hoặc tham số xử lý có thể đổi trong khi timestamp của source vẫn giữ nguyên.

Muốn build tăng dần đáng tin cậy, cần nhận diện đầu vào thực sự của từng bước, biết loại thay đổi nào được Ant tự phát hiện và chủ động vô hiệu hóa đầu ra khi có thay đổi nằm ngoài cơ chế timestamp.

## 1. Ant quyết định biên dịch tăng dần như thế nào?

Task **javac** quét source tree và destination tree. Theo cơ chế thông thường, một tệp Java được đưa vào danh sách biên dịch khi:

- Không tìm thấy class file tương ứng.
- Class file tương ứng cũ hơn source.

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"/>
~~~

Với cấu trúc:

~~~text
src/main/java/
└── com/example/
    ├── App.java
    └── Service.java

build/classes/
└── com/example/
    ├── App.class
    └── Service.class
~~~

Nếu Service.java mới hơn Service.class, Ant đưa source đó vào lần biên dịch. Nếu App.class đã mới hơn hoặc bằng App.java, Ant có thể bỏ qua App.java.

Cơ chế này dựa trên **tên tệp và timestamp**. Ant không so sánh toàn bộ nội dung source với class, cũng không tự suy luận mọi thay đổi trong cấu hình build.

Vì thế, incremental javac trả lời câu hỏi: “Tệp source này có cần biên dịch theo trạng thái của cặp source/class tương ứng không?”. Nó không trả lời đầy đủ các câu hỏi như:

- Source đã bị xóa thì class cũ cần dọn thế nào?
- Class khác phụ thuộc vào API vừa thay đổi có cần biên dịch lại không?
- Compiler option đã đổi thì toàn bộ class có còn hợp lệ không?
- Một JAR trong classpath bị thay thế hoặc bị gỡ thì cần làm gì?

## 2. Nguồn bị xóa: class file cũ không tự biến mất

Giả sử lần build đầu có:

~~~text
src/main/java/com/example/
├── App.java
├── LegacyService.java
└── UserService.java
~~~

Sau khi biên dịch, thư mục đích chứa:

~~~text
build/classes/com/example/
├── App.class
├── LegacyService.class
└── UserService.class
~~~

Sau đó, developer xóa **LegacyService.java** vì chức năng đã bị loại bỏ. Khi chạy javac lần tiếp theo, Ant quét source và không còn thấy LegacyService.java. Không có source nào tương ứng để đưa vào danh sách biên dịch.

Tuy nhiên, **LegacyService.class** cũ vẫn nằm trong thư mục build/classes. Task javac không xem thư mục đích là bản sao cần đồng bộ tuyệt đối với source tree; nó không tự xóa mọi class file không còn source.

Hậu quả có thể thấy ở bước đóng gói:

~~~xml
<jar destfile="dist/application.jar"
     basedir="build/classes"/>
~~~

JAR vẫn có thể chứa LegacyService.class, dù source đã bị xóa khỏi repository. Class cũ có thể gây nhầm lẫn, làm artifact chứa API không còn được duy trì hoặc khiến runtime vẫn tải được một lớp lẽ ra đã bị loại bỏ.

### Xóa thư mục class trước khi biên dịch lại

Cách đơn giản và chắc chắn nhất khi cần loại bỏ đầu ra mồ côi là clean destination trước khi biên dịch:

~~~xml
<target name="clean-classes">
    <delete dir="build/classes"/>
</target>

<target name="compile-clean" depends="clean-classes">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Cách này biên dịch lại toàn bộ source nhưng đảm bảo class file cũ không còn sót trong destination.

Nếu chỉ muốn build tăng dần trong trường hợp không có source bị xóa, có thể giữ target compile thông thường và gọi clean khi đổi tên/xóa lớp. Tuy nhiên, quy trình CI hoặc release quan trọng nên có một đường build sạch định kỳ để xác nhận artifact được tạo từ đúng tập source hiện tại.

### Khi đổi tên source

Đổi tên một lớp thường tương đương với xóa source cũ và thêm source mới:

~~~text
Trước:
LegacyService.java

Sau:
ModernService.java
~~~

Incremental javac có thể biên dịch ModernService.java vì class tương ứng chưa tồn tại, nhưng LegacyService.class vẫn còn. Vì vậy, đổi tên cũng cần dọn output cũ hoặc clean module.

### Xóa generated source

Nếu source được sinh từ schema, template hoặc annotation processor, việc xóa đầu vào có thể làm source sinh ra từ lần trước không còn hợp lệ. Hãy xác định rõ thư mục generated thuộc quyền sở hữu của bước nào và dọn nó khi đầu vào bị loại bỏ.

Không nên xóa một thư mục generated dùng chung nếu có nhiều target hoặc module cùng ghi vào đó. Tốt hơn là dùng thư mục đầu ra riêng cho từng generator hoặc từng module, sau đó dọn đúng thư mục đó.

## 3. Tài nguyên bị xóa và task sync

Vấn đề đầu ra mồ côi không chỉ xuất hiện với class. Task **copy** thường sao chép tệp mới hoặc đã thay đổi, nhưng không tự xóa mọi tệp đích không còn trong nguồn.

Ví dụ:

~~~xml
<copy todir="build/resources">
    <fileset dir="src/main/resources"/>
</copy>
~~~

Nếu source có **config/old.properties** ở lần build trước, tệp đó đã được copy sang build/resources. Sau đó source bị xóa, lần copy tiếp theo không có tệp để copy, nhưng bản đích cũ vẫn có thể tồn tại.

Nếu muốn thư mục đích phản ánh tập resource hiện tại, dùng task **sync**:

~~~xml
<sync todir="build/resources">
    <fileset dir="src/main/resources"/>
</sync>
~~~

Sync thực hiện đồng bộ theo tập resource được chọn và loại bỏ các tệp đích không còn tương ứng trong tập nguồn.

Cần dùng sync với thư mục đích chuyên biệt. Nếu nhiều nguồn khác nhau cùng ghi vào một thư mục đích, sync theo một nguồn có thể xóa các tệp do nguồn khác tạo ra. Hãy chia destination theo module hoặc theo loại tài nguyên để phạm vi dọn dẹp rõ ràng.

| Nhu cầu | Cách xử lý |
|---|---|
| Chỉ copy tệp mới hoặc thay đổi | copy |
| Đích phải phản ánh chính xác tập nguồn hiện tại | sync |
| Xóa toàn bộ class cũ trước khi biên dịch lại | delete destination rồi javac |
| Dọn một thư mục generated do một target sở hữu | delete đúng thư mục generated rồi chạy generator |

## 4. Dependency thay đổi: source tiêu thụ không nhất thiết mới hơn

Một lớp Java có thể phụ thuộc vào API của lớp khác. Nếu API thay đổi, source của lớp tiêu thụ có thể cần biên dịch lại dù bản thân source đó không sửa.

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

Ban đầu, Service.class được biên dịch dựa trên API của Model. Sau đó Model thay đổi kiểu trả về hoặc chữ ký phương thức. Model.java mới hơn Model.class nên javac nhận ra Model cần biên dịch lại.

Nhưng Service.java không đổi và Service.class vẫn mới hơn Service.java. Kiểm tra timestamp đơn thuần không nhất thiết đưa Service.java vào lần biên dịch, dù class tiêu thụ có thể không còn tương thích với API mới.

Đây là lý do cần phân biệt **source timestamp** và **class dependency**.

### Dùng task depend trước javac

Task **depend** của Ant phân tích các class file để xác định lớp nào phụ thuộc vào class đã lỗi thời. Khi phát hiện dependency bị ảnh hưởng, nó xóa class file của lớp tiêu thụ. Sau đó javac nhìn thấy class file tương ứng không còn và biên dịch lại source.

~~~xml
<depend srcdir="src/main/java"
        destdir="build/classes"
        cache="build/depend-cache"/>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"/>
~~~

Thứ tự phải là:

~~~text
Source hoặc dependency thay đổi
            |
            v
       depend phân tích
            |
            v
  Xóa class file bị ảnh hưởng
            |
            v
       javac quét source
            |
            v
  Biên dịch source chưa có class
~~~

Task depend không biên dịch source. Nó chỉ phân tích quan hệ class và vô hiệu hóa class file cần được tạo lại.

### Dependency bắc cầu và closure

Giả sử:

~~~text
A sử dụng B
B sử dụng C
~~~

Khi C thay đổi, depend mặc định chỉ xử lý quan hệ trực tiếp. Đặt **closure="true"** để xét cả các phụ thuộc bắc cầu:

~~~xml
<depend srcdir="src/main/java"
        destdir="build/classes"
        cache="build/depend-cache"
        closure="true"/>
~~~

Closure có thể xóa nhiều class hơn và làm tăng số source cần biên dịch lại. Chỉ bật khi mức bao phủ đó cần thiết; với nhiều dự án, quan hệ trực tiếp thường đã đủ.

### Theo dõi JAR trong classpath

Nếu source của ứng dụng phụ thuộc vào JAR nội bộ được build ở module khác, task depend có thể nhận classpath để kiểm tra dependency với class và JAR bên ngoài:

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

Khi JAR được cập nhật và có timestamp mới hơn class file tiêu thụ, depend có thể vô hiệu hóa các class phụ thuộc để javac biên dịch lại.

Chỉ đưa vào classpath của depend những thư viện có khả năng thay đổi và cần theo dõi. Việc phân tích mọi thư viện bên thứ ba hoặc JDK runtime có thể làm build chậm mà không đem lại lợi ích tương ứng.

## 5. Giới hạn của dependency analysis

Task depend hữu ích nhưng không phải một bộ phân tích source hoàn chỉnh. Nó đọc tham chiếu được ghi trong bytecode, không phân tích mã nguồn Java. Vì vậy, một số thay đổi có thể không được phát hiện:

- Compiler tối ưu và loại bỏ một tham chiếu class khỏi bytecode.
- Class không public khiến việc liên kết class file với source khó xác định.
- Thay đổi hằng primitive compile-time đã được compiler nhúng trực tiếp vào bytecode của lớp sử dụng.
- Dependency không nằm trong source, destination hoặc classpath mà depend được cấu hình để xét.
- JAR bị thay thế nhưng timestamp không mới hơn class tiêu thụ.
- Một classpath entry bị gỡ bỏ hoặc thứ tự classpath thay đổi; depend không thể suy ra đầy đủ ý nghĩa của cấu hình classpath mới chỉ từ các entry hiện tại.

Ví dụ hằng compile-time:

~~~java
public final class BuildFlags {
    public static final boolean DEBUG = false;
}
~~~

Khi một lớp khác sử dụng BuildFlags.DEBUG, compiler có thể nhúng trực tiếp giá trị false vào bytecode. Nếu hằng đổi thành true, class tiêu thụ có thể không còn tham chiếu tới BuildFlags trong bytecode. Depend không nhất thiết phát hiện được lớp đó cần biên dịch lại.

Với những thay đổi quan trọng như vậy, clean build là lựa chọn an toàn. Đừng coi depend là bảo đảm tuyệt đối rằng mọi thay đổi API hoặc mọi thay đổi dependency đều được phát hiện.

## 6. Thay đổi cấu hình compiler: timestamp source không đủ

Giả sử lần đầu build dùng:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       source="11"
       target="11"
       debug="true"
       includeantruntime="false"/>
~~~

Sau đó cấu hình đổi sang:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       source="17"
       target="17"
       debug="false"
       includeantruntime="false"/>
~~~

Các source có thể không thay đổi và class file cũ vẫn mới hơn source. Cơ chế timestamp của javac không tự coi thay đổi các thuộc tính source, target hoặc debug là lý do để biên dịch lại tất cả source.

Những thay đổi cấu hình thường cần vô hiệu hóa output gồm:

- Phiên bản compiler hoặc JDK.
- **source**, **target** hoặc **release**.
- **debug**, **debuglevel**, **deprecation** và các cờ compiler khác.
- Encoding của source.
- Annotation processor hoặc compiler argument.
- Classpath, module path hoặc thứ tự thư viện.
- Cấu hình generator, filter hoặc công cụ xử lý resource.
- Các property quyết định nội dung source hoặc resource được sinh.

Nếu không dọn output, thư mục class có thể chứa các class được biên dịch bằng nhiều cấu hình khác nhau. Điều này làm kết quả khó dự đoán và có thể khiến CI khác máy developer.

### Cách 1: clean khi cấu hình thay đổi

Cách trực tiếp nhất là xóa thư mục class trước khi biên dịch khi compiler option hoặc toolchain đổi:

~~~xml
<target name="clean-classes">
    <delete dir="build/classes"/>
</target>

<target name="compile-clean" depends="clean-classes">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           source="17"
           target="17"
           debug="false"
           includeantruntime="false"/>
</target>
~~~

Cách này dễ hiểu và đáng tin cậy, nhưng không tận dụng incremental compilation cho lần chạy đó.

### Cách 2: dùng output directory riêng theo cấu hình

Nếu nhiều cấu hình cần tồn tại song song, có thể đưa các giá trị quan trọng vào tên thư mục output:

~~~xml
<property name="java.release" value="17"/>
<property name="debug.info" value="false"/>
<property name="classes.dir"
          location="build/classes-java${java.release}-debug-${debug.info}"/>

<target name="compile">
    <mkdir dir="${classes.dir}"/>

    <javac srcdir="src/main/java"
           destdir="${classes.dir}"
           release="${java.release}"
           debug="${debug.info}"
           includeantruntime="false"/>
</target>
~~~

Khi release hoặc debug đổi, Ant dùng một destination khác. Class của cấu hình cũ không bị trộn vào output mới.

Cách này phù hợp với build nhiều biến thể, nhưng tên thư mục phải bao gồm mọi cấu hình quan trọng. Nếu classpath, compiler version hoặc annotation processor đổi mà tên thư mục không phản ánh thay đổi đó, output vẫn có thể bị dùng lại sai.

### Cách 3: theo dõi file cấu hình bằng uptodate và stamp

Task **uptodate** có thể so sánh timestamp của các file cấu hình với một marker file. Nếu file cấu hình mới hơn marker, build xóa class cũ trước khi biên dịch.

Ví dụ:

~~~xml
<property name="src.dir" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>
<property name="build.dir" location="build"/>
<property name="compile.stamp" location="build/compile-config.stamp"/>

<target name="detect-compile-config">
    <uptodate property="compile.config.current"
              targetfile="${compile.stamp}">
        <srcfiles dir="${basedir}">
            <include name="build.xml"/>
            <include name="config/compiler.properties"/>
        </srcfiles>
    </uptodate>
</target>

<target name="invalidate-classes"
        depends="detect-compile-config"
        unless="compile.config.current">
    <delete dir="${classes.dir}"/>
    <delete file="${compile.stamp}"/>
</target>

<target name="compile" depends="invalidate-classes">
    <mkdir dir="${classes.dir}"/>

    <depend srcdir="${src.dir}"
            destdir="${classes.dir}"
            cache="${build.dir}/depend-cache"/>

    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"
           source="17"
           target="17"/>

    <!-- Chỉ cập nhật stamp nếu javac hoàn tất thành công -->
    <touch file="${compile.stamp}"/>
</target>
~~~

Cách hoạt động:

1. Target detect-compile-config so sánh build.xml và compiler.properties với stamp.
2. Nếu stamp chưa tồn tại hoặc file cấu hình mới hơn, property compile.config.current không được thiết lập.
3. Target invalidate-classes chạy vì property chưa tồn tại và xóa class cũ.
4. Target compile chạy depend rồi javac.
5. Chỉ sau khi javac hoàn tất thành công, touch cập nhật stamp.

Nếu file cấu hình không đổi và stamp vẫn mới hơn, target invalidate-classes được bỏ qua. Javac tiếp tục dùng kiểm tra tăng dần và depend xử lý các thay đổi class dependency mà nó có thể phát hiện.

**Giới hạn của cách stamp:** uptodate so sánh các file được khai báo. Nó không tự phát hiện giá trị property truyền trực tiếp từ dòng lệnh như -Djava.release=17 đổi thành -Djava.release=21 nếu không có file nào tương ứng thay đổi. Hãy lưu cấu hình build trong file được theo dõi, đưa giá trị cấu hình vào tên output directory, hoặc chủ động clean khi thay đổi property trên dòng lệnh.

## 7. Classpath thay đổi: thêm, sửa và gỡ thư viện

Classpath có thể thay đổi theo nhiều cách khác nhau:

| Thay đổi | Rủi ro với incremental build | Cách xử lý |
|---|---|---|
| JAR hiện tại được cập nhật và timestamp mới hơn | Class tiêu thụ có thể cần biên dịch lại | Khai báo JAR trong classpath của depend |
| JAR được thay bằng nội dung mới nhưng giữ timestamp cũ | Depend có thể không nhận ra thay đổi | Clean hoặc dùng output/config fingerprint |
| Thêm JAR mới | Source có thể phân giải kiểu theo thư viện mới | Đưa thay đổi classpath vào cấu hình được theo dõi; clean nếu kết quả phân giải có thể đổi |
| Gỡ JAR khỏi classpath | Class cũ có thể vẫn tồn tại dù dependency đã bị loại | Clean và biên dịch lại để phát hiện lỗi thiếu dependency |
| Đổi thứ tự JAR | Lớp cùng tên có thể được nạp từ nguồn khác | Coi là thay đổi cấu hình và vô hiệu hóa output |
| Đổi phiên bản JDK/compiler | Class có thể mang target hoặc bytecode khác | Dùng output riêng hoặc clean |

Task depend có thể theo dõi những class/JAR được khai báo trong classpath và vô hiệu hóa class tiêu thụ cũ hơn phần tử dependency. Tuy nhiên, nó không thay thế việc theo dõi toàn bộ cấu hình classpath. Đặc biệt, việc xóa hoặc sắp xếp lại entry có thể làm thay đổi cách compiler phân giải tên lớp mà không có timestamp đầu vào mới để so sánh.

## 8. Thay đổi cấu hình generator và resource processing

Build Ant thường có nhiều bước ngoài javac:

~~~text
schema / template / config
          |
          v
     code generator
          |
          v
   generated Java source
          |
          v
        javac
          |
          v
     class files
          |
          v
       package
~~~

Nếu template hoặc cấu hình generator thay đổi nhưng source được sinh ra không được cập nhật timestamp, các bước sau có thể bỏ qua đầu vào mới. Tương tự, nếu filter hoặc encoding của bước copy resource thay đổi, tệp đích cũ có thể không được ghi lại nếu task không biết cấu hình đã đổi.

Một cách tổ chức là đặt đầu ra generator trong thư mục riêng và xóa trước khi sinh lại khi template/config thay đổi:

~~~xml
<target name="generate-sources">
    <delete dir="build/generated-sources"/>
    <mkdir dir="build/generated-sources"/>

    <!-- Gọi generator với template và config hiện tại -->
</target>
~~~

Với resource cần phản ánh chính xác nguồn, dùng sync vào destination chuyên biệt:

~~~xml
<target name="sync-resources">
    <sync todir="build/resources">
        <fileset dir="src/main/resources">
            <exclude name="local/**"/>
        </fileset>
    </sync>
</target>
~~~

Khi nội dung resource hoặc quy tắc chọn thay đổi, cần đảm bảo destination được đồng bộ theo đúng tập đầu vào hiện tại. Nếu thay đổi encoding/filter nhưng source timestamp không đổi, hãy buộc bước xử lý resource chạy lại bằng cách theo dõi file cấu hình hoặc clean destination.

## 9. Clean build và incremental build phục vụ hai mục đích khác nhau

Clean build xóa output và tạo lại từ đầu. Incremental build giữ lại output cũ và chỉ cập nhật phần Ant xác định là cần thiết.

| Tiêu chí | Incremental build | Clean build |
|---|---|---|
| Tốc độ khi thay đổi nhỏ | Thường nhanh hơn | Thường chậm hơn |
| Source bị xóa | Có thể để lại class cũ | Output cũ bị xóa |
| Dependency thay đổi | Cần depend và cấu hình classpath phù hợp | Biên dịch lại toàn bộ |
| Compiler option đổi | Cần invalidation rõ ràng | Tự nhiên được áp dụng cho toàn bộ output |
| Output cũ/mồ côi | Có thể còn nếu không dọn | Được loại khỏi destination |
| Kiểm tra tính tái lập | Không đủ nếu chỉ dựa vào timestamp | Là phép kiểm tra tốt hơn cho quy trình build sạch |

Không nhất thiết phải clean trước mọi lần build developer. Nhưng nên có một target clean rõ ràng và một lượt clean build trong CI hoặc trước release để phát hiện trạng thái cũ bị sót.

Ví dụ:

~~~xml
<target name="clean">
    <delete dir="build"/>
    <delete dir="dist"/>
</target>

<target name="compile">
    <!-- Biên dịch tăng dần -->
</target>

<target name="compile-clean" depends="clean,compile"/>
~~~

Có thể gọi:

~~~bash
ant compile
ant compile-clean
~~~

Lưu ý thứ tự dependency target trong build thực tế: target clean phải hoàn thành trước target compile. Nếu target compile còn phụ thuộc prepare hoặc generate-sources, hãy đưa dependency đó vào compile để cả hai cách gọi đều thực hiện đúng chuỗi.

## 10. Ví dụ build.xml: kết hợp depend, cấu hình và đồng bộ resource

Ví dụ sau minh họa một module Java có class output, resource output và compiler config file được theo dõi:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="build" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="resource.src" location="src/main/resources"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="resources.dir" location="${build.dir}/resources"/>
    <property name="depend.cache" location="${build.dir}/depend-cache"/>
    <property name="compile.stamp" location="${build.dir}/compile-config.stamp"/>

    <path id="compile.path">
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="detect-config">
        <uptodate property="compile.config.current"
                  targetfile="${compile.stamp}">
            <srcfiles dir="${basedir}">
                <include name="build.xml"/>
                <include name="config/compiler.properties"/>
            </srcfiles>
        </uptodate>
    </target>

    <target name="invalidate-output"
            depends="detect-config"
            unless="compile.config.current">
        <delete dir="${classes.dir}"/>
        <delete file="${compile.stamp}"/>
    </target>

    <target name="prepare" depends="invalidate-output">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${resources.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <depend srcdir="${src.dir}"
                destdir="${classes.dir}"
                cache="${depend.cache}">
            <classpath refid="compile.path"/>
        </depend>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               source="17"
               target="17">
            <classpath refid="compile.path"/>
        </javac>

        <touch file="${compile.stamp}"/>
    </target>

    <target name="resources" depends="prepare">
        <sync todir="${resources.dir}">
            <fileset dir="${resource.src}">
                <exclude name="local/**"/>
            </fileset>
        </sync>
    </target>

    <target name="build" depends="compile,resources">
        <echo message="Incremental build completed."/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="dist"/>
    </target>

</project>
~~~

Trong ví dụ:

- **detect-config** xác định file cấu hình compiler có thay đổi so với stamp hay không.
- **invalidate-output** xóa class khi cấu hình đầu vào được theo dõi thay đổi.
- **depend** vô hiệu hóa class tiêu thụ khi dependency class/JAR được theo dõi thay đổi.
- **javac** biên dịch source chưa có class hoặc class cũ hơn source.
- **touch** cập nhật stamp sau khi javac thành công.
- **sync** đồng bộ resource và xóa resource đích không còn trong nguồn.
- **clean** xóa toàn bộ output để tạo lại từ đầu.

Đây là khung minh họa. Nếu classpath thay đổi theo file JAR, nên đưa danh sách hoặc phiên bản thư viện vào một file cấu hình được theo dõi bởi stamp. Nếu classpath có entry bị gỡ hoặc đổi thứ tự, hãy vô hiệu hóa output rõ ràng. Nếu property compiler được truyền từ dòng lệnh, cần đưa giá trị đó vào cấu hình được theo dõi hoặc chọn destination theo cấu hình.

## 11. Dấu hiệu cho thấy incremental output đã cũ

Khi build tăng dần cho kết quả khác với clean build, hãy kiểm tra những dấu hiệu sau:

| Triệu chứng | Khả năng nguyên nhân |
|---|---|
| Class đã xóa khỏi source nhưng vẫn có trong JAR | Class file cũ còn trong destination |
| Đổi tên lớp nhưng cả tên cũ và mới đều có trong artifact | Output cũ chưa được dọn |
| API của thư viện thay đổi nhưng class tiêu thụ vẫn cũ | Chưa chạy depend hoặc dependency không nằm trong classpath theo dõi |
| Đổi source/target/release nhưng bytecode không đổi | javac bỏ qua source vì timestamp không báo cũ |
| Gỡ JAR nhưng build vẫn thành công hoặc runtime vẫn tải class cũ | Class cũ trong output hoặc classpath thay đổi chưa được invalidation |
| Xóa resource nguồn nhưng resource vẫn có trong output | copy không dọn tệp đích mồ côi |
| Sửa template nhưng generated source không đổi | Generator không được chạy lại hoặc config/template không được khai báo là input |
| Clean build thành công nhưng incremental build thất bại | Thiếu dependency hoặc invalidation trong mô hình build |

Một cách chẩn đoán hữu ích là so sánh danh sách file của output incremental và output clean. Nếu clean build loại bỏ được class hoặc resource mà incremental build vẫn giữ, đó là dấu hiệu có đầu ra mồ côi hoặc quy tắc invalidation chưa đầy đủ.

## 12. Nguyên tắc thiết kế build tăng dần đáng tin cậy

- Coi output là kết quả của một tập đầu vào cụ thể, gồm source, dependency, cấu hình và công cụ.
- Nhớ rằng javac chọn source theo sự tồn tại và timestamp của class file tương ứng; nó không tự xóa class của source đã bị xóa.
- Clean destination hoặc dùng quy trình đồng bộ khi source bị xóa/đổi tên.
- Dùng sync cho resource khi thư mục đích phải phản ánh chính xác tập nguồn hiện tại.
- Đặt depend trước javac khi cần vô hiệu hóa class tiêu thụ bị ảnh hưởng bởi class dependency đã thay đổi.
- Khai báo classpath của depend cho các JAR nội bộ có thể thay đổi.
- Không dựa vào depend để phát hiện mọi thay đổi classpath, hằng compile-time hoặc mọi quan hệ source.
- Coi compiler option, JDK, encoding, annotation processor và generator configuration là đầu vào của build.
- Theo dõi file cấu hình bằng uptodate/stamp hoặc tách output directory theo cấu hình.
- Với property truyền qua dòng lệnh, hãy lưu giá trị vào một cấu hình được theo dõi hoặc clean khi giá trị thay đổi.
- Có target clean và chạy clean build định kỳ trong CI hoặc trước release.
- Kiểm tra artifact cuối cùng để bảo đảm không còn class/resource đã bị xóa khỏi nguồn.

Incremental build chỉ đáng tin khi mọi thay đổi có thể làm đầu ra khác đi đều có cách kích hoạt xử lý lại. Timestamp giúp nhận ra nhiều source đã sửa, depend xử lý thêm một phần thay đổi class dependency, còn clean, sync và cấu hình stamp xử lý những thay đổi mà hai cơ chế đó không bao quát. Khi mô hình hóa rõ các đầu vào và phạm vi output, Ant có thể vừa giữ được tốc độ build tăng dần vừa tránh sử dụng class hoặc resource cũ.

## Tài liệu tham khảo

- [Apache Ant — Javac Task](https://ant.apache.org/manual/Tasks/javac.html)
- [Apache Ant — Depend Task](https://ant.apache.org/manual/Tasks/depend.html)
- [Apache Ant — UpToDate Task](https://ant.apache.org/manual/Tasks/uptodate.html)
- [Apache Ant — Sync Task](https://ant.apache.org/manual/Tasks/sync.html)
- [Apache Ant — Copy Task](https://ant.apache.org/manual/Tasks/copy.html)

