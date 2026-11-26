# Cấu hình quyền native access cho classpath hoặc named module theo JDK triển khai

**Native access** là quyền cho phép một module Java thực hiện các thao tác tương tác với mã hoặc dữ liệu bên ngoài JVM. Quyền này liên quan đến các thao tác có thể làm mất một phần bảo đảm an toàn của Java, chẳng hạn gọi restricted methods trong Foreign Function & Memory (FFM) API, khai báo phương thức JNI hoặc nạp thư viện native.

Tùy chọn **--enable-native-access** được giới thiệu cùng FFM API final trong Java 22. Từ JDK 24, JEP 472 mở rộng chính sách native access để bao phủ cả JNI. Vì vậy, khi cấu hình ứng dụng cần phân biệt JDK 22–23 với JDK 24 trở lên, đồng thời xác định mã native nằm trên classpath hay trong named module.

## 1. Native access kiểm soát điều gì?

Native access cho phép mã Java đi qua ranh giới của JVM để làm việc với thư viện native hoặc vùng nhớ ngoài runtime. Những thao tác này hữu ích khi tích hợp thư viện C/C++, driver, hệ thống mã hóa, xử lý ảnh, cơ sở dữ liệu hoặc phần mềm cần tương tác trực tiếp với phần cứng.

Một số thao tác có thể yêu cầu native access:

- Gọi các restricted methods trong FFM API, ví dụ **Linker.downcallHandle(...)**, **Linker.upcallStub(...)**, **SymbolLookup.libraryLookup(...)**, **MemorySegment.reinterpret(...)** hoặc **AddressLayout.withTargetLayout(...)**.
- Khai báo và sử dụng phương thức Java có từ khóa **native** theo JNI trên JDK 24 trở lên.
- Nạp thư viện native bằng **System.load(...)** hoặc **System.loadLibrary(...)** theo chính sách JNI từ JDK 24 trở lên.
- Cấp native access cho module được tạo động thông qua **ModuleLayer.Controller.enableNativeAccess(...)**. Bản thân phương thức này cũng là restricted method.

Không phải mọi thao tác FFM đều cần quyền này. Tạo segment bằng **Arena.allocate(...)**, tạo heap segment bằng **MemorySegment.ofArray(...)**, hoặc đọc/ghi một segment hợp lệ bằng **get(...)** và **set(...)** không tự yêu cầu bật native access. Quyền được kiểm tra khi chương trình gọi các thao tác thuộc nhóm bị hạn chế hoặc thực hiện native access theo chính sách của JDK.

Native access cũng không phải cơ chế cấp quyền truy cập file, mạng hay quyền hệ điều hành. Nó chỉ kiểm soát việc module Java được phép thực hiện các thao tác native thuộc phạm vi chính sách của JVM.

## 2. Chính sách thay đổi theo phiên bản JDK

| Phiên bản runtime | Phạm vi native access | Hành vi mặc định và cách cấu hình |
|---|---|---|
| **JDK 22–23** | Chính sách áp dụng cho restricted methods của FFM API. JNI chưa được đưa vào cơ chế hạn chế native access của JEP 472. | Gọi restricted method mặc định phát cảnh báo. Dùng **--enable-native-access** để cấp quyền và bỏ cảnh báo cho module được chọn. Khi đã chỉ định tùy chọn này, module ngoài danh sách gọi restricted method sẽ nhận **IllegalCallerException**. |
| **JDK 24 trở lên** | JEP 472 mở rộng native access sang JNI, gồm khai báo native methods và nạp thư viện native; restricted methods của FFM vẫn thuộc phạm vi này. | Mặc định **--illegal-native-access=warn**: thao tác chưa được cấp quyền vẫn chạy và phát cảnh báo tối đa một lần cho mỗi module. Có thể dùng **deny** để biến access chưa được cấp quyền thành **IllegalCallerException**. |
| **JDK 25 LTS và JDK 27** | Áp dụng chính sách JDK 24 trở lên. | Dùng **--enable-native-access** để khai báo rõ module cần quyền. Dùng **--illegal-native-access=deny** trong kiểm thử nâng cấp; tài liệu JDK 27 đánh dấu tùy chọn này sẽ bị loại bỏ trong một bản phát hành tương lai. |

Có hai điều cần nhớ khi nâng cấp:

1. **--enable-native-access** xác định module được phép dùng native access.
2. **--illegal-native-access** (từ JDK 24) xác định JVM xử lý thế nào khi module thực hiện native access mà chưa được cấp quyền.

Ở JDK 24 trở lên, chế độ mặc định **warn** vẫn cho phép thao tác tiếp tục. Cảnh báo cho biết ứng dụng đang dựa vào quyền chưa được khai báo tường minh. Khi chuyển sang **deny**, cùng thao tác đó sẽ ném **IllegalCallerException**.

Không truyền **--illegal-native-access** cho JDK 22 hoặc JDK 23 vì các bản này chưa hỗ trợ tùy chọn đó.

## 3. Cấu hình cho ứng dụng chạy trên classpath

Mã chạy trên classpath thuộc **unnamed module**. Giá trị đặc biệt **ALL-UNNAMED** dùng để cấp native access cho tất cả mã thuộc các unnamed module trong tiến trình.

### Chạy classpath trực tiếp

~~~shell
java --enable-native-access=ALL-UNNAMED -cp "<classpath>" com.example.Main
~~~

Thay **<classpath>** bằng danh sách thư mục và JAR của ứng dụng. Dấu phân cách các phần tử classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS.

Ví dụ chạy một ứng dụng đóng gói thành executable JAR:

~~~shell
java --enable-native-access=ALL-UNNAMED -jar app.jar
~~~

Tùy chọn JVM phải được đặt trước **-cp**, **-jar**, tên lớp chính hoặc tùy chọn khởi chạy module. Nếu đặt sau tên lớp hoặc sau tên JAR, đối số có thể được chuyển vào chương trình thay vì được JVM hiểu là tùy chọn.

### Khi nào dùng ALL-UNNAMED?

Dùng **ALL-UNNAMED** khi mã cần native access nằm trên classpath, ví dụ:

- Ứng dụng Java không dùng module path.
- Thư viện FFM/JNI được đặt trong thư mục dependency trên classpath.
- Executable JAR chạy bằng **java -jar**.
- Ứng dụng framework đóng gói nhiều dependency thành một JAR và các lớp đó thuộc unnamed module.

**ALL-UNNAMED** cấp quyền cho toàn bộ mã trên classpath của tiến trình, bao gồm cả dependency bên thứ ba. Nếu chỉ một thư viện cần native access, phạm vi này rộng hơn cần thiết. Khi có thể, hãy chuyển riêng thư viện đó sang module path để cấp quyền theo tên module.

### Cấp quyền qua manifest của executable JAR

Với executable JAR chạy trên classpath, có thể thêm thuộc tính sau vào phần main attributes của file manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Enable-Native-Access: ALL-UNNAMED

~~~

Khi khởi chạy bằng **java -jar app.jar**, JVM đọc thuộc tính manifest và cấp native access cho mã trên classpath. Thuộc tính **Enable-Native-Access** chỉ chấp nhận giá trị **ALL-UNNAMED**; không dùng tên named module ở đây.

Nếu cấu hình manifest không phù hợp với cách đóng gói ứng dụng, truyền tùy chọn trực tiếp trong lệnh chạy hoặc cấu hình launcher của môi trường triển khai.

## 4. Cấu hình cho named module

Mã được nạp từ module path và có tên module xác định được gọi là **named module**. Khi cấp native access, dùng đúng tên module được khai báo trong **module-info.java** hoặc tên automatic module mà JVM suy ra.

Ví dụ cấu trúc module:

~~~text
mods/
  com.example.app.jar
  com.example.nativebridge.jar
~~~

Giả sử:

- **com.example.app** là module ứng dụng, có mã gọi FFM restricted methods.
- **com.example.nativebridge** là module chứa lớp khai báo JNI native methods hoặc thực hiện việc nạp thư viện native.

Có thể cấp quyền cho cả hai module:

~~~shell
java --enable-native-access=com.example.app,com.example.nativebridge --module-path mods --module com.example.app/com.example.Main
~~~

Tên module được phân cách bằng dấu phẩy, không phải tên package hoặc tên lớp chính. Có thể cấp quyền cho một module hoặc nhiều module cùng lúc.

### Chọn đúng module cần cấp quyền

Cấp quyền cho module thực hiện native access:

- Nếu mã trong **com.example.app** gọi **Linker.downcallHandle(...)**, module **com.example.app** cần native access.
- Nếu lớp trong **com.example.nativebridge** khai báo phương thức **native** hoặc nạp thư viện JNI, module **com.example.nativebridge** cần native access từ JDK 24 trở lên.
- Nếu một module khác cũng trực tiếp gọi restricted methods hoặc thực hiện native access, thêm module đó vào danh sách.

Không mặc định chỉ cần cấp quyền cho module chứa **main()**. Vị trí mã gọi restricted method hoặc thực hiện JNI mới quyết định module cần quyền.

### Xác định tên automatic module

Một JAR không có **module-info.class** nhưng được đặt trên module path sẽ được xử lý như automatic module. Tên module được suy ra từ tên JAR, trừ khi JAR khai báo thuộc tính **Automatic-Module-Name**.

Dùng lệnh sau để kiểm tra tên module thực tế:

~~~shell
jar --describe-module --file libs/native-bridge.jar
~~~

Ví dụ nếu kết quả cho biết tên automatic module là **native.bridge**, có thể cấp quyền bằng:

~~~shell
java --enable-native-access=native.bridge --module-path mods --module com.example.app/com.example.Main
~~~

Đặt dependency lên module path không bắt buộc JAR phải có **module-info.java**. Tuy nhiên, cần kiểm tra tên module và quan hệ phụ thuộc để cấu hình quyền chính xác.

## 5. Khác biệt quan trọng khi cấu hình JDK 22 và JDK 24+

### JDK 22–23: phạm vi FFM restricted methods

Ở JDK 22, native access được dùng để kiểm soát việc gọi các restricted methods của FFM API. Nếu ứng dụng chạy trên classpath và gọi restricted method, có thể cấp quyền như sau:

~~~shell
java --enable-native-access=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Nếu ứng dụng chạy dưới named module:

~~~shell
java --enable-native-access=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

Nếu một module không nằm trong danh sách đã cấp quyền gọi restricted method khi tùy chọn này hiện diện, JVM ném **IllegalCallerException**. Do đó, cần xác định đầy đủ module dùng FFM restricted methods trước khi chỉ định danh sách.

Nếu không bật tùy chọn, JDK 22 mặc định phát cảnh báo khi restricted methods được gọi. Đây là cảnh báo về thao tác nhạy cảm, không phải bằng chứng rằng mọi thao tác FFM đều nguy hiểm hoặc cần native access.

### JDK 24 trở lên: FFM và JNI cùng chịu chính sách

Từ JDK 24, JEP 472 đưa việc sử dụng JNI vào chính sách native access. Vì vậy, ứng dụng dùng **native** methods hoặc nạp thư viện native cũng cần cấu hình quyền cho module tương ứng.

Lệnh chạy ứng dụng classpath trên JDK 24+:

~~~shell
java --enable-native-access=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Lệnh chạy ứng dụng module path:

~~~shell
java --enable-native-access=com.example.app,com.example.nativebridge --module-path mods --module com.example.app/com.example.Main
~~~

Nếu một module chưa được cấp quyền, mặc định **warn** cho phép thao tác tiếp tục và cảnh báo tối đa một lần cho module đó. Khi kiểm thử với **deny**, thao tác chưa được cấp quyền sẽ thất bại:

~~~shell
java --illegal-native-access=deny -cp app.jar com.example.Main
~~~

Khi ứng dụng cần một số module được cấp quyền, kết hợp hai tùy chọn:

~~~shell
java --enable-native-access=com.example.app,com.example.nativebridge --illegal-native-access=deny --module-path mods --module com.example.app/com.example.Main
~~~

Chế độ **deny** hữu ích để phát hiện dependency hoặc module chưa được cấu hình. Không xem **--illegal-native-access=allow** như cách sửa cấu hình thiếu quyền trong sản phẩm; hãy tìm module thực hiện thao tác và cấp quyền đúng phạm vi. Trên JDK 27, tùy chọn **--illegal-native-access** vẫn có nhưng tài liệu đánh dấu sẽ bị loại bỏ trong tương lai, nên dùng nó như công cụ kiểm tra trong quá trình chuyển đổi.

## 6. Cấu hình native access trong môi trường chạy ứng dụng

Native access là tùy chọn của JVM runtime. Chỉ thêm nó vào lệnh **javac** không có tác dụng cấp quyền khi ứng dụng chạy. Cần truyền tùy chọn đến đúng tiến trình Java thực thi mã FFM/JNI.

### Maven Surefire

Nếu kiểm thử chạy trên classpath, thêm JVM arguments vào tiến trình test fork:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--enable-native-access=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Khi test chạy bằng JDK 24 trở lên, có thể thêm **--illegal-native-access=deny** để tìm các module đang thực hiện native access mà chưa được cấp quyền:

~~~xml
<argLine>--enable-native-access=ALL-UNNAMED --illegal-native-access=deny</argLine>
~~~

Nếu test chạy trên named module, thay **ALL-UNNAMED** bằng danh sách tên module cần quyền.

### Gradle Test

Với test chạy trên classpath:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs("--enable-native-access=ALL-UNNAMED")
}
~~~

Trên JDK 24 trở lên, thêm chế độ kiểm tra nghiêm ngặt trong cấu hình test:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

Nếu cấu hình build có cả unit test và integration test chạy bằng các JVM riêng, phải truyền quyền cho từng tiến trình cần native access. Việc cấu hình JVM của Gradle hoặc Maven không tự động cấu hình tiến trình production được khởi chạy ở môi trường khác.

### Biến môi trường JDK_JAVA_OPTIONS

Có thể truyền tùy chọn cho Java launcher qua biến môi trường **JDK_JAVA_OPTIONS**:

~~~shell
JDK_JAVA_OPTIONS="--enable-native-access=ALL-UNNAMED"
~~~

Trên PowerShell:

~~~powershell
$env:JDK_JAVA_OPTIONS = "--enable-native-access=ALL-UNNAMED"
~~~

Launcher sẽ nối các tùy chọn này vào command line của các lần chạy **java** trong môi trường đó. Cách này hữu ích khi nền tảng triển khai không dễ sửa lệnh khởi chạy, nhưng có thể ảnh hưởng đến nhiều ứng dụng hoặc công cụ Java chạy trong cùng môi trường. Với hệ thống có nhiều service, cấu hình ở từng service thường dễ kiểm soát hơn.

## 7. Kiểm tra module nào cần native access

Từ JDK 24, công cụ **jnativescan** có thể phân tích JAR trên classpath hoặc module path để tìm các restricted method call và khai báo phương thức **native**.

Quét một ứng dụng classpath:

~~~shell
jnativescan --class-path app.jar --release 27 --print-native-access
~~~

Quét module path, bắt đầu từ module ứng dụng và các dependency của nó:

~~~shell
jnativescan --module-path mods --add-modules com.example.app --release 27 --print-native-access
~~~

Thay **27** bằng phiên bản runtime dự kiến triển khai. Với JDK 25 LTS, dùng **--release 25** để công cụ đối chiếu theo tập restricted methods của JDK 25.

Kết quả của **--print-native-access** là danh sách module có sử dụng native functionality. Nếu một JAR được quét từ classpath, công cụ hiển thị **ALL-UNNAMED**. Nếu JAR là named module hoặc automatic module trên module path, kết quả hiển thị tên module tương ứng.

Có thể bỏ **--print-native-access** để xem cây chi tiết hơn, gồm JAR, lớp và phương thức có sử dụng restricted methods hoặc khai báo **native**. Công cụ phân tích tĩnh giúp xác định module cần xem xét, nhưng không thay thế kiểm thử tích hợp cho các đường gọi được tạo động hoặc nạp theo cấu hình runtime.

## 8. Lựa chọn phạm vi cấp quyền

| Kiểu triển khai | Cấu hình nên dùng |
|---|---|
| Ứng dụng thuần classpath | **--enable-native-access=ALL-UNNAMED** |
| Ứng dụng modular, một module gọi FFM restricted methods | **--enable-native-access=com.example.app** |
| Ứng dụng modular, nhiều module có native functionality | **--enable-native-access=com.example.app,com.example.nativebridge** |
| Dependency không modular hóa nhưng được đặt trên module path | Dùng tên automatic module thực tế |
| Executable JAR chạy bằng **java -jar** | Tùy chọn command line hoặc manifest **Enable-Native-Access: ALL-UNNAMED** |
| JDK 24+ đang chuẩn bị nâng cấp | Cấp quyền cần thiết và chạy test với **--illegal-native-access=deny** |

Nên cấp quyền cho đúng module cần dùng. **ALL-UNNAMED** thuận tiện cho ứng dụng classpath nhưng có phạm vi rộng, vì mọi thư viện trên classpath đều thuộc unnamed module. Khi một dependency native độc lập, cân nhắc chuyển JAR đó sang module path để giới hạn quyền ở automatic module hoặc named module tương ứng.

## 9. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Bật **--enable-preview** để dùng FFM | FFM API final từ JDK 22; native access là chính sách riêng, không phải preview. |
| Dùng **--add-opens** hoặc **--add-exports** thay native access | Hai tùy chọn đó điều chỉnh truy cập package/module; chúng không cấp native access. |
| Dùng **--illegal-access** để xử lý cảnh báo JNI/FFM | **--illegal-access** thuộc cơ chế truy cập phản chiếu cũ; chính sách native access dùng **--enable-native-access** và, từ JDK 24, **--illegal-native-access**. |
| Chỉ cấp quyền cho module chứa **main()** | Phải xác định module thực sự gọi restricted methods, khai báo native methods hoặc nạp thư viện native. |
| Nghĩ **ALL-UNNAMED** bao gồm named modules | Giá trị này chỉ áp dụng cho mã trên classpath. Named module phải được chỉ định bằng tên module. |
| Nghĩ thêm **--enable-native-access** vào lệnh **javac** là đủ | Đây là cấu hình runtime; phải truyền đến JVM chạy ứng dụng hoặc test. |
| Bỏ qua cảnh báo mặc định trên JDK 24+ | Cảnh báo cho biết module chưa được cấp quyền tường minh; hãy kiểm thử với **--illegal-native-access=deny** và cập nhật cấu hình. |

## 10. Quy trình triển khai và nâng cấp

1. **Xác định phiên bản runtime.** Kiểm tra JDK thực sự dùng để chạy service, test và container. Không chỉ dựa vào phiên bản compiler trên máy phát triển.
2. **Tìm các điểm dùng native functionality.** Kiểm tra FFM restricted methods, khai báo JNI native methods và nơi gọi **System.load(...)** hoặc **System.loadLibrary(...)**.
3. **Xác định module chứa mã native.** Phân biệt unnamed module trên classpath, named module và automatic module trên module path.
4. **Cấp quyền ở phạm vi hẹp.** Dùng **ALL-UNNAMED** cho classpath khi cần; dùng danh sách tên module cho ứng dụng modular.
5. **Kiểm tra trên JDK 24+.** Chạy **jnativescan** và chạy integration test với **--illegal-native-access=deny** để tìm các quyền chưa khai báo.
6. **Đồng bộ cấu hình runtime.** Cập nhật lệnh chạy service, cấu hình test, container hoặc custom runtime. Kiểm tra cả môi trường production và môi trường kiểm thử.
7. **Đánh giá lại sau khi nâng cấp JDK.** Danh sách restricted methods và chính sách native access có thể thay đổi theo release; đối chiếu tài liệu của JDK mục tiêu.

Không nên cấp native access toàn cục chỉ để loại bỏ cảnh báo mà chưa biết thư viện nào cần quyền. Native code có thể làm JVM crash hoặc gây hỏng bộ nhớ nếu dùng sai. Xác định module, cấp quyền có chủ đích và kiểm thử với chính sách nghiêm ngặt giúp quá trình nâng cấp JDK dễ kiểm soát hơn.

## Tài liệu tham khảo chính thức

- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): thay đổi chính sách JNI từ JDK 24.
- [The java Command — JDK 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html): cú pháp **--enable-native-access** và hành vi trên JDK 22.
- [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): cú pháp native access, **--illegal-native-access** và các tùy chọn launcher hiện hành.
- [Restricted Methods — JDK 27 Core Libraries Guide](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html): danh sách FFM restricted methods, cách cấp quyền và lựa chọn phạm vi module.
- [Migrating from JDK 8 to Later JDK Releases — JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): cách chuẩn bị ứng dụng cho chính sách native access và công cụ rà soát.
- [The jnativescan Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jnativescan.html): phân tích JAR, module path và tìm module dùng native functionality.
- [Java Native Interface Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/intro.html): tổng quan JNI và yêu cầu native access.
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): thuộc tính manifest **Enable-Native-Access**.

