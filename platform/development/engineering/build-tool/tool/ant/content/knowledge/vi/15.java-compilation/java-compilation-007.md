# Chọn executable và giới hạn bộ nhớ cho trình biên dịch ngoài trong Apache Ant

Task javac của Apache Ant có thể biên dịch mã nguồn Java ngay trong JVM đang chạy Ant hoặc khởi chạy một tiến trình compiler riêng. Khi cần chọn chính xác bộ JDK dùng để biên dịch, cô lập bộ nhớ compiler hoặc điều chỉnh heap cho dự án lớn, có thể bật fork và chỉ định executable của javac.

Ba thuộc tính cần phân biệt:

- fork quyết định compiler có chạy trong tiến trình riêng hay không.
- executable chỉ định chương trình compiler bên ngoài được gọi khi fork được bật.
- memoryInitialSize và memoryMaximumSize đặt bộ nhớ ban đầu và giới hạn heap cho JVM chạy compiler được fork.

Các thuộc tính bộ nhớ này không điều chỉnh heap của chính tiến trình Ant. Hiểu đúng ranh giới đó giúp xử lý lỗi thiếu bộ nhớ ở đúng tiến trình.

## 1. Hai cách Ant gọi trình biên dịch Java

Task javac cung cấp một giao diện thống nhất để biên dịch mã nguồn. Tùy cấu hình, Ant có thể gọi compiler theo hai cách.

### 1.1. Biên dịch trong JVM của Ant

Mặc định, fork là false. Ant sử dụng compiler thông qua API trong cùng JVM đang chạy build:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false" />
~~~

Ở chế độ này:

- Compiler chạy trong tiến trình Ant.
- Các thuộc tính executable, memoryInitialSize và memoryMaximumSize không được dùng để khởi chạy một JVM compiler riêng.
- Bộ nhớ dành cho compiler nằm trong heap của JVM Ant.
- Việc chọn compiler adapter được điều khiển bởi thuộc tính compiler của task hoặc property build.compiler.

Cách này thuận tiện cho build thông thường vì không phải quản lý thêm một tiến trình ngoài. Tuy nhiên, nếu cần gọi một file javac cụ thể hoặc muốn cấu hình heap riêng cho compiler, chế độ mặc định không đáp ứng được mục tiêu đó.

### 1.2. Biên dịch trong tiến trình riêng

Đặt fork="true" để Ant khởi chạy compiler ở tiến trình riêng:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       includeantruntime="false" />
~~~

Khi đó, Ant gọi chương trình compiler bên ngoài. Nếu không chỉ định executable, Ant sử dụng lệnh javac theo cơ chế tìm executable của môi trường, thường là thông qua PATH.

Chế độ fork phù hợp khi:

- Cần chọn một JDK cụ thể để biên dịch.
- Muốn tách heap compiler khỏi heap của Ant.
- Muốn truyền các tùy chọn JVM dành cho compiler.
- Cần chạy một compiler executable bên ngoài theo cấu hình của môi trường build.

Đổi lại, build phải khởi chạy thêm tiến trình. Cần bảo đảm executable tồn tại, có quyền chạy và tương thích với mã nguồn cùng các tùy chọn javac được sử dụng.

## 2. Chọn compiler adapter và chọn executable là hai việc khác nhau

Trong task javac, thuộc tính compiler và executable có mục đích riêng.

| Thuộc tính | Ý nghĩa |
|---|---|
| compiler | Chọn adapter mà Ant dùng để giao tiếp với một loại compiler hoặc phiên bản compiler |
| fork | Chọn chạy compiler trong JVM Ant hay trong tiến trình riêng |
| executable | Chỉ định đường dẫn tới chương trình compiler bên ngoài khi fork=true |

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       compiler="modern"
       fork="true"
       executable="/opt/jdk-21/bin/javac" />
~~~

compiler="modern" chọn compiler adapter của Ant; executable chỉ ra file chương trình thực sự được chạy. Không nên nhầm compiler="..." với đường dẫn đến javac.

Nếu dự án cần sử dụng một bản JDK cụ thể, hãy chỉ định executable rõ ràng và kiểm tra phiên bản của file đó. Điều này tránh trường hợp Ant vô tình sử dụng một javac khác trên PATH.

Tên và các adapter compiler được hỗ trợ có thể thay đổi theo phiên bản Ant. Với các dự án mới dùng javac tiêu chuẩn, adapter mặc định thường là lựa chọn phù hợp; chỉ đặt compiler khi có lý do tương thích cụ thể.

## 3. Chỉ định executable của javac

Thuộc tính executable nhận đường dẫn hoặc tên chương trình compiler. Khi dùng đường dẫn tuyệt đối, buildfile xác định rõ bộ JDK cần sử dụng.

Ví dụ trên Linux hoặc macOS:

~~~xml
<property name="jdk.home" location="/opt/jdk-21" />
<property name="javac.executable"
          location="${jdk.home}/bin/javac" />

<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="true"
           executable="${javac.executable}"
           includeantruntime="false"
           encoding="UTF-8" />
</target>
~~~

Ví dụ trên Windows:

~~~xml
<property name="jdk.home"
          location="C:/Program Files/Java/jdk-21" />
<property name="javac.executable"
          location="${jdk.home}/bin/javac.exe" />

<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="true"
           executable="${javac.executable}"
           includeantruntime="false"
           encoding="UTF-8" />
</target>
~~~

Đường dẫn trong ví dụ cần được thay bằng vị trí JDK thực tế trên máy hoặc máy build. Với đường dẫn chứa khoảng trắng, hãy khai báo property bằng location hoặc đặt đường dẫn đúng cách trong cấu hình XML; Ant xử lý thuộc tính này như một đường dẫn chương trình thay vì một chuỗi lệnh shell tự ghép.

### 3.1. Dùng JAVA_HOME làm nguồn cấu hình

Có thể lấy vị trí JDK từ biến môi trường JAVA_HOME:

~~~xml
<property environment="env" />
<property name="jdk.home" value="${env.JAVA_HOME}" />
~~~

Sau đó đặt executable phù hợp với hệ điều hành. Ví dụ trên Unix-like:

~~~xml
<property name="javac.executable"
          location="${jdk.home}/bin/javac" />
~~~

Trên Windows:

~~~xml
<property name="javac.executable"
          location="${jdk.home}/bin/javac.exe" />
~~~

Cần bảo đảm JAVA_HOME trỏ đến thư mục JDK có chứa bin/javac. Nếu JAVA_HOME trỏ đến một runtime chỉ có java mà không có compiler, Ant không thể biên dịch bằng executable đó.

Không nên mặc định rằng java.home luôn chính là thư mục JDK mong muốn. Giá trị này có thể trỏ đến runtime đang chạy Ant; nếu cần một JDK khác, hãy cấu hình jdk.home riêng.

### 3.2. Kiểm tra executable

Trước khi chạy build, có thể kiểm tra chương trình được chỉ định:

~~~bash
/opt/jdk-21/bin/javac -version
~~~

Trên Windows:

~~~powershell
& "C:/Program Files/Java/jdk-21/bin/javac.exe" -version
~~~

Lệnh phải chạy thành công và hiển thị phiên bản javac mong muốn. Nếu không chạy được, kiểm tra lại đường dẫn, quyền thực thi, biến môi trường và bản cài JDK.

## 4. Giới hạn bộ nhớ cho compiler bằng memoryInitialSize và memoryMaximumSize

Khi fork="true", task javac hỗ trợ hai thuộc tính để cấu hình heap của JVM chạy compiler:

- memoryInitialSize: kích thước heap ban đầu.
- memoryMaximumSize: giới hạn heap tối đa.

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="${javac.executable}"
       memoryInitialSize="256m"
       memoryMaximumSize="2g"
       includeantruntime="false" />
~~~

Các giá trị như 256m hoặc 2g biểu diễn dung lượng bộ nhớ. Ant chuyển các thiết lập này thành tùy chọn JVM dành cho tiến trình compiler, tương ứng với -J-Xms và -J-Xmx khi gọi javac.

Ý nghĩa:

- Xms là heap ban đầu mà JVM compiler yêu cầu.
- Xmx là giới hạn heap tối đa JVM compiler được phép sử dụng.
- memoryInitialSize không phải cam kết rằng compiler sẽ dùng hết dung lượng đó ngay khi khởi động.
- memoryMaximumSize giới hạn heap, không phải tổng toàn bộ RAM của tiến trình; bộ nhớ native và các vùng ngoài heap vẫn có thể tiêu thụ thêm tài nguyên.

Các thuộc tính này chỉ có tác dụng khi compiler được fork. Nếu fork=false, đặt memoryInitialSize hoặc memoryMaximumSize không làm tăng heap của Ant.

### 4.1. Chọn mức heap hợp lý

Không có một con số phù hợp cho mọi dự án. Mức heap phụ thuộc số lượng mã nguồn, độ phức tạp của kiểu dữ liệu, annotation processor, plugin compiler và tài nguyên của máy build.

Một số mức tham khảo để bắt đầu thử nghiệm:

| Quy mô / đặc điểm build | Heap tối đa tham khảo |
|---|---:|
| Dự án nhỏ, ít module | 512m |
| Dự án vừa, nhiều thư viện | 1g |
| Dự án lớn, nhiều module hoặc annotation processor | 2g hoặc cao hơn nếu máy có đủ RAM |

Đây chỉ là điểm bắt đầu, không phải định mức bắt buộc. Hãy theo dõi mức dùng bộ nhớ và thời gian biên dịch trên môi trường thực tế trước khi tăng heap.

Nếu đặt memoryMaximumSize quá thấp, compiler có thể kết thúc với lỗi OutOfMemoryError. Nếu đặt quá cao, nhiều tiến trình build đồng thời có thể gây áp lực lên RAM và hệ điều hành.

### 4.2. Chỉ đặt memoryMaximumSize khi cần

Có thể chỉ định giới hạn tối đa mà không đặt heap ban đầu:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="${javac.executable}"
       memoryMaximumSize="1536m"
       includeantruntime="false" />
~~~

Khi không chỉ định memoryInitialSize, JVM compiler sử dụng mặc định của JVM. Cách này phù hợp khi chỉ muốn giới hạn mức tối đa để tránh compiler chiếm quá nhiều bộ nhớ.

Nếu cần kiểm soát cả mức ban đầu và tối đa, đặt cả hai. Không nên đặt Xms bằng Xmx một cách máy móc; điều đó khiến JVM yêu cầu heap lớn ngay từ đầu và có thể làm tăng áp lực RAM khi chạy nhiều build đồng thời.

## 5. Ví dụ hoàn chỉnh: fork javac với executable và heap riêng

Ví dụ dưới đây minh họa một dự án Java sử dụng JDK 21, thư viện trong thư mục lib và compiler chạy ở tiến trình riêng.

Cấu trúc thư mục:

~~~text
inventory/
├── build.xml
├── src/
│   └── main/
│       └── java/
│           └── com/example/inventory/Main.java
├── lib/
│   ├── library-a.jar
│   └── library-b.jar
└── build/
    └── classes/
~~~

Buildfile trên Linux hoặc macOS:

~~~xml
<project name="inventory" default="compile" basedir=".">
    <property name="jdk.home" location="/opt/jdk-21" />
    <property name="javac.executable"
              location="${jdk.home}/bin/javac" />
    <property name="src.dir" location="src/main/java" />
    <property name="classes.dir" location="build/classes" />
    <property name="lib.dir" location="lib" />

    <path id="compile.classpath">
        <fileset dir="${lib.dir}">
            <include name="**/*.jar" />
        </fileset>
    </path>

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}" />

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               fork="true"
               executable="${javac.executable}"
               memoryInitialSize="256m"
               memoryMaximumSize="2g"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>
</project>
~~~

Chạy:

~~~bash
ant clean compile
~~~

Ant thực hiện target clean trước, sau đó compile. Task javac khởi chạy executable đã cấu hình, truyền classpath từ các JAR trong lib và cấp giới hạn heap tối đa 2 GB cho JVM compiler.

Đối với Windows, thay jdk.home bằng đường dẫn JDK trên máy và executable bằng bin/javac.exe. Các phần còn lại của buildfile có thể giữ nguyên nếu đường dẫn được khai báo bằng property phù hợp.

## 6. Phân biệt bộ nhớ compiler và bộ nhớ của Ant

Đây là điểm quan trọng khi xử lý OutOfMemoryError.

Khi fork=true, có ít nhất hai tiến trình JVM liên quan:

~~~text
Máy build
  |
  +-- JVM chạy Ant
  |     |
  |     +-- Đọc build.xml
  |     +-- Tổ chức task và dependency
  |     +-- Điều phối compiler
  |
  +-- JVM chạy javac (compiler fork)
        |
        +-- Đọc mã nguồn
        +-- Phân tích và biên dịch
        +-- Tạo file .class
~~~

memoryMaximumSize điều chỉnh heap của JVM chạy compiler. Nó không thay đổi heap của JVM chạy Ant.

Nếu lỗi xuất hiện trong compiler, ví dụ javac báo OutOfMemoryError khi phân tích mã nguồn hoặc chạy annotation processor, hãy xem xét tăng memoryMaximumSize.

Nếu chính tiến trình Ant hết bộ nhớ khi đọc buildfile, xử lý nhiều resource hoặc thực hiện các task khác, cần điều chỉnh heap của JVM Ant, thường thông qua biến môi trường ANT_OPTS hoặc cách khởi chạy JVM phù hợp. Ví dụ:

~~~bash
ANT_OPTS="-Xms256m -Xmx1g" ant compile
~~~

Trên Windows PowerShell:

~~~powershell
$env:ANT_OPTS = "-Xms256m -Xmx1g"
ant compile
~~~

ANT_OPTS được dùng khi khởi chạy Ant; các cờ trong đó không thay thế memoryMaximumSize của compiler fork. Ngược lại, memoryMaximumSize cũng không sửa được lỗi thiếu heap của chính Ant.

## 7. Khi nào nên bật fork?

Bật fork khi có yêu cầu cụ thể:

- Cần chọn executable javac ở một JDK riêng.
- Muốn giới hạn heap compiler độc lập với Ant.
- Cần cô lập compiler khỏi JVM điều phối build.
- Muốn kiểm soát rõ phiên bản compiler được gọi trên CI.

Giữ fork=false khi compiler mặc định phù hợp, build không cần chỉ định executable và không có nhu cầu tách bộ nhớ. Chạy trong cùng JVM thường đơn giản hơn và tránh chi phí tạo tiến trình riêng.

Việc bật fork không tự động làm compiler nhanh hơn. Quá trình khởi chạy tiến trình có chi phí; hiệu năng thực tế còn phụ thuộc vào số file, dependency, annotation processor, filesystem và khả năng tái sử dụng kết quả của task javac.

## 8. Những lỗi thường gặp và cách xử lý

### 8.1. executable không được sử dụng

Nếu đã khai báo executable nhưng fork=false, Ant không khởi chạy executable đó theo cấu hình fork. Hãy đặt fork="true" khi muốn gọi chương trình bên ngoài.

### 8.2. Không tìm thấy javac

Kiểm tra:

- Đường dẫn executable có đúng tên file và phần mở rộng không?
- JAVA_HOME hoặc jdk.home có trỏ đến JDK không?
- Tiến trình chạy Ant có quyền thực thi file không?
- Đường dẫn có chứa khoảng trắng hoặc ký tự đặc biệt cần xử lý không?
- Máy CI có cài JDK tương ứng không?

Có thể chạy trực tiếp javac -version để xác nhận executable hoạt động.

### 8.3. Vẫn thiếu bộ nhớ dù đã tăng memoryMaximumSize

Trước tiên, xác định tiến trình nào báo lỗi. Nếu compiler fork báo OutOfMemoryError, hãy xem giới hạn heap, annotation processor và kích thước dự án. Nếu Ant JVM báo lỗi, điều chỉnh ANT_OPTS hoặc JVM options dùng để chạy Ant.

Cũng cần bảo đảm máy có đủ RAM. Tăng Xmx lên mức lớn hơn RAM khả dụng có thể làm hệ thống swap hoặc kết thúc tiến trình.

### 8.4. Đặt memoryMaximumSize nhưng quên fork

Hai thuộc tính memoryInitialSize và memoryMaximumSize chỉ dùng cho compiler được fork. Khi fork=false, chúng không thay đổi heap của JVM Ant. Hãy bật fork nếu muốn áp dụng giới hạn riêng cho compiler.

### 8.5. Dùng nhầm java thay cho javac

Thuộc tính executable của task javac phải trỏ đến chương trình compiler javac, không phải java. Trên JDK thông thường, javac nằm trong thư mục bin cạnh chương trình java.

### 8.6. Compiler executable khác phiên bản Java chạy ứng dụng

JDK dùng để biên dịch có thể khác JDK dùng để chạy Ant hoặc ứng dụng. Hãy ghi rõ JDK được yêu cầu và kiểm tra phiên bản compiler thực tế. Nếu dự án đặt yêu cầu về API hoặc bytecode, cấu hình thêm release hoặc source/target phù hợp với phiên bản Ant và JDK đang dùng.

### 8.7. Đặt heap quá lớn trên CI

Một pipeline có thể chạy nhiều job song song. Nếu mỗi compiler được cấp 4 GB heap, nhiều tiến trình đồng thời có thể vượt quá RAM máy build. Hãy tính tổng tài nguyên cho tất cả job và chọn giới hạn phù hợp với mức song song thực tế.

## 9. Thực hành tốt

- **Chỉ bật fork khi có nhu cầu.** Không nên thêm tiến trình ngoài nếu compiler mặc định đã đáp ứng dự án.
- **Chỉ định executable từ cấu hình JDK rõ ràng.** Tránh phụ thuộc vào một javac bất kỳ trong PATH khi CI cần phiên bản xác định.
- **Dùng property cho đường dẫn JDK.** Tách jdk.home và javac.executable để dễ cấu hình theo môi trường.
- **Phân biệt compiler và executable.** compiler chọn adapter; executable chọn chương trình bên ngoài.
- **Đặt giới hạn heap theo số liệu.** Bắt đầu từ mức phù hợp, quan sát log và mức dùng RAM rồi điều chỉnh.
- **Không nhầm heap compiler với heap Ant.** memoryMaximumSize chỉ dành cho JVM compiler fork; ANT_OPTS điều chỉnh JVM chạy Ant.
- **Giữ classpath rõ ràng.** Dùng Path có id để compiler nhận đúng thư mục lớp và các JAR cần thiết.
- **Kiểm tra phiên bản javac thực tế.** Chạy executable với -version khi chẩn đoán môi trường.
- **Tính đến build song song.** Tổng heap của nhiều compiler fork có thể vượt quá RAM dù từng job riêng lẻ hoạt động tốt.
- **Ghi rõ yêu cầu môi trường.** Tài liệu build nên chỉ ra JDK tối thiểu, đường dẫn cấu hình và cách chạy trên Windows/Linux/macOS.

## 10. Kết luận

Trong Apache Ant, fork="true" yêu cầu task javac chạy compiler ở tiến trình riêng. Khi đó, executable chọn chương trình javac cụ thể, còn memoryInitialSize và memoryMaximumSize cấu hình heap ban đầu và tối đa cho JVM compiler. Các thuộc tính này không điều chỉnh bộ nhớ của JVM chạy Ant.

Hãy chọn fork khi cần kiểm soát JDK hoặc tách bộ nhớ compiler. Đặt executable trỏ đúng đến javac trong JDK, chọn heap theo kích thước dự án và tài nguyên máy, đồng thời phân biệt lỗi thiếu bộ nhớ của compiler với lỗi thiếu bộ nhớ của Ant. Cấu hình rõ ràng giúp build ổn định và dễ tái hiện giữa máy lập trình viên và CI.

## Tài liệu tham khảo

- [Apache Ant Javac Task](https://ant.apache.org/manual/Tasks/javac.html)
- [Apache Ant Running Ant](https://ant.apache.org/manual/running.html)
- [Java Compiler javac — Command Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)

