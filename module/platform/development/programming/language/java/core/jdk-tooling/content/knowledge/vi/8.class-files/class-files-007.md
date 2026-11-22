# Debug information trong Java class file

## 1. Debug information là gì?

Debug information là metadata tùy chọn được compiler ghi vào tệp bytecode `.class` để debugger và công cụ phân tích có thể liên hệ bytecode với mã nguồn. Nhờ thông tin này, lập trình viên có thể đặt breakpoint theo dòng, xem tên biến cục bộ, theo dõi phạm vi biến và đọc stack trace có vị trí nguồn rõ ràng hơn.

Mã Java vẫn có thể chạy khi class file không chứa debug information. JVM không cần tên biến cục bộ hay số dòng nguồn để thực thi bytecode. Những thông tin này chủ yếu phục vụ quá trình phát triển, kiểm thử và điều tra lỗi.

Các nhóm thông tin thường gặp gồm:

- Tên tệp nguồn dùng để biên dịch class.
- Ánh xạ giữa vị trí lệnh bytecode và số dòng nguồn.
- Tên, kiểu và phạm vi tồn tại của biến cục bộ.
- Chữ ký generic của biến cục bộ khi kiểu generic bị xóa ở runtime.

Trong Java, debug information được điều khiển chủ yếu bằng các tùy chọn của compiler `javac`: `-g`, `-g:none` và `-g:<options>`. Đây là tùy chọn lúc biên dịch; thêm tùy chọn JVM khi chạy không thể khôi phục thông tin đã không được ghi vào class file.

## 2. Debug information được lưu ở đâu trong class file?

Java class file có cấu trúc gồm header, constant pool, khai báo lớp, field, method và các attribute. Debug information được lưu trong những attribute tùy chọn ở cấp lớp hoặc bên trong attribute `Code` của từng phương thức.

| Attribute | Vị trí | Thông tin lưu |
|---|---|---|
| `SourceFile` | Cấp class | Tên tệp nguồn được dùng để biên dịch class. |
| `LineNumberTable` | Bên trong `Code` của method | Ánh xạ bytecode offset với số dòng nguồn. |
| `LocalVariableTable` | Bên trong `Code` của method | Tên biến cục bộ, descriptor/kiểu JVM, slot và phạm vi bytecode mà biến có hiệu lực. |
| `LocalVariableTypeTable` | Bên trong `Code` của method | Chữ ký generic của biến cục bộ khi kiểu đầy đủ không thể biểu diễn bằng descriptor JVM thông thường. |

Các attribute này là tùy chọn. Công cụ biên dịch có thể ghi một phần hoặc không ghi chúng tùy cấu hình.

### `SourceFile`

`SourceFile` lưu tên tệp nguồn, ví dụ `DebugInfoDemo.java`. Nó không nhúng toàn bộ mã nguồn vào class file và thông thường cũng không lưu đường dẫn đầy đủ tới thư mục dự án.

Debugger cần có mã nguồn tương ứng trên máy đang debug để hiển thị nội dung dòng lệnh. Nếu chỉ có class file mà thiếu source tương ứng, debugger có thể biết tên tệp và số dòng nhưng không thể hiển thị đúng đoạn mã nguồn.

### `LineNumberTable`

`LineNumberTable` liên kết bytecode offset với số dòng trong tệp nguồn. Một dòng Java có thể tạo ra nhiều lệnh bytecode; compiler ghi các điểm ánh xạ để debugger có thể dừng ở vị trí gần dòng nguồn tương ứng.

Thông tin này cũng giúp JVM hiển thị số dòng trong stack trace. Nếu class file không có ánh xạ dòng, stack trace có thể không có số dòng cụ thể hoặc hiển thị `Unknown Source` tùy thông tin còn lại.

### `LocalVariableTable`

`LocalVariableTable` lưu thông tin biến cục bộ, thường gồm:

- `Start`: bytecode offset bắt đầu phạm vi biến.
- `Length`: độ dài phạm vi bytecode mà biến còn hiệu lực.
- `Slot`: vị trí lưu biến trong local-variable array của frame.
- `Name`: tên biến trong mã nguồn.
- `Signature`: descriptor kiểu ở dạng JVM, ví dụ `I` cho `int`, `Ljava/lang/String;` cho `String`.

Biến có thể chỉ tồn tại trong một phần phương thức. Vì vậy, debugger chỉ hiển thị biến khi vị trí thực thi đang nằm trong phạm vi được ghi trong bảng. Một biến đã hết phạm vi hoặc chưa được khởi tạo có thể không xuất hiện như mong đợi.

### `LocalVariableTypeTable`

Java generic sử dụng type erasure. Ví dụ, kiểu `List<String>` thường có descriptor JVM là `Ljava/util/List;`, giống với `List<Integer>` sau khi xóa tham số kiểu.

`LocalVariableTypeTable` có thể lưu generic signature như `Ljava/util/List<Ljava/lang/String;>;` để debugger và công cụ bytecode biết kiểu generic ban đầu của biến. Attribute này bổ sung cho `LocalVariableTable`; nó không thay đổi kiểu runtime của đối tượng.

## 3. Các tùy chọn debug của `javac`

`javac` hỗ trợ ba cách cấu hình chính:

| Tùy chọn | Kết quả |
|---|---|
| Không chỉ định `-g` | Mặc định compiler tạo thông tin tên tệp nguồn và số dòng (`source`, `lines`); không yêu cầu ghi tên biến cục bộ. |
| `-g` | Ghi tất cả nhóm debug information mà compiler hỗ trợ, gồm `source`, `lines` và `vars`. |
| `-g:none` | Không ghi các nhóm debug information do tùy chọn `-g` điều khiển. |
| `-g:source` | Chỉ ghi tên tệp nguồn. |
| `-g:lines` | Chỉ ghi ánh xạ số dòng. |
| `-g:vars` | Chỉ ghi thông tin biến cục bộ. |
| `-g:source,lines` | Ghi tên tệp nguồn và ánh xạ số dòng. |
| `-g:source,lines,vars` | Ghi cả ba nhóm thông tin. |

Trong cách dùng mặc định, `javac` thường ghi `SourceFile` và `LineNumberTable` để stack trace có vị trí dòng. Nếu cần debugger xem tên biến cục bộ, hãy bật `-g` hoặc `-g:vars`.

Ví dụ:

~~~bash
# Toàn bộ debug information
javac --release 17 -g -d out src/DebugInfoDemo.java

# Chỉ thông tin source và line
javac --release 17 -g:source,lines -d out src/DebugInfoDemo.java

# Chỉ thông tin biến cục bộ
javac --release 17 -g:vars -d out src/DebugInfoDemo.java

# Không ghi debug information
javac --release 17 -g:none -d out src/DebugInfoDemo.java
~~~

`-g` không có nghĩa là bật chế độ debug của JVM lúc chạy. Nó yêu cầu compiler ghi thêm metadata vào artifact ngay từ đầu.

## 4. Ví dụ chạy được: so sánh class có và không có debug information

Tạo file `src/DebugInfoDemo.java`:

~~~java
import java.util.List;

public class DebugInfoDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Ada", "Linus");
        int count = names.size();
        System.out.println(names.get(0) + ":" + count);
    }
}
~~~

Tạo hai thư mục output riêng và biên dịch:

~~~bash
mkdir -p out-debug out-no-debug

# Bản có đầy đủ debug information
javac --release 17 -g -d out-debug src/DebugInfoDemo.java

# Bản không có debug information
javac --release 17 -g:none -d out-no-debug src/DebugInfoDemo.java
~~~

Chạy bản có debug information:

~~~bash
java -cp out-debug DebugInfoDemo
~~~

Stdout:

~~~text
Ada:2
~~~

Chạy bản không có debug information:

~~~bash
java -cp out-no-debug DebugInfoDemo
~~~

Stdout:

~~~text
Ada:2
~~~

Hai bản vẫn thực thi cùng logic và cho cùng kết quả. Sự khác nhau nằm ở metadata trong class file: bản `-g` có thêm bảng dòng và biến cục bộ; bản `-g:none` bỏ các attribute debug tương ứng.

Trên Windows PowerShell, có thể tạo thư mục đầu ra bằng:

~~~powershell
New-Item -ItemType Directory -Force out-debug, out-no-debug | Out-Null
javac --release 17 -g -d out-debug src/DebugInfoDemo.java
javac --release 17 -g:none -d out-no-debug src/DebugInfoDemo.java
java -cp out-debug DebugInfoDemo
java -cp out-no-debug DebugInfoDemo
~~~

Nên dùng thư mục output riêng khi so sánh các cấu hình. Nếu biên dịch lại vào cùng một thư mục mà không dọn class file cũ, artifact cũ có thể khiến kết quả kiểm tra không phản ánh tùy chọn vừa dùng.

## 5. Kiểm tra debug information bằng `javap`

`javap` là công cụ disassembler của JDK. Tùy chọn `-v` (`-verbose`) hiển thị attribute trong class file; `-l` hiển thị thông tin dòng và biến cục bộ; `-p` hiển thị cả thành viên private.

Kiểm tra bản có debug information:

~~~bash
javap -v -l -classpath out-debug DebugInfoDemo
~~~

Trong kết quả, tìm các attribute:

~~~text
SourceFile: "DebugInfoDemo.java"

LineNumberTable:
  ...

LocalVariableTable:
  ...

LocalVariableTypeTable:
  ...
~~~

Dấu `...` ở trên chỉ phần nội dung chi tiết do `javap` in ra; bytecode offset, số dòng, slot và phạm vi cụ thể phụ thuộc vào mã nguồn cũng như phiên bản compiler.

Kiểm tra bản không có debug information:

~~~bash
javap -v -l -classpath out-no-debug DebugInfoDemo
~~~

Bản này không có `SourceFile`, `LineNumberTable`, `LocalVariableTable` và `LocalVariableTypeTable` được tạo bởi các tùy chọn debug của `javac`.

Có thể chỉ xem phần line/local-variable bằng:

~~~bash
javap -l -classpath out-debug DebugInfoDemo
~~~

Hoặc lọc trên Linux/macOS:

~~~bash
javap -v -l -classpath out-debug DebugInfoDemo | grep -E "SourceFile|LineNumberTable|LocalVariableTable|LocalVariableTypeTable"
~~~

Trên PowerShell:

~~~powershell
javap -v -l -classpath out-debug DebugInfoDemo | Select-String -Pattern "SourceFile|LineNumberTable|LocalVariableTable|LocalVariableTypeTable"
~~~

Đây là cách kiểm tra artifact thực tế trong thư mục build hoặc trong JAR phát hành. Không nên chỉ dựa vào cấu hình Maven/Gradle vì một module hoặc task biên dịch riêng có thể dùng tùy chọn khác.

## 6. Debugger sử dụng thông tin này như thế nào?

Debugger cần ánh xạ giữa mã nguồn và bytecode để cung cấp trải nghiệm gỡ lỗi thuận tiện:

- **Breakpoint theo dòng:** `LineNumberTable` giúp debugger xác định bytecode offset tương ứng với dòng nguồn.
- **Step over / step into:** thông tin dòng giúp debugger điều khiển bước thực thi theo vị trí mã nguồn.
- **Variables view:** `LocalVariableTable` cung cấp tên, kiểu và phạm vi biến cục bộ.
- **Generic type display:** `LocalVariableTypeTable` giúp hiển thị tham số kiểu như `String` trong `List<String>`.
- **Stack trace:** `SourceFile` và `LineNumberTable` hỗ trợ hiển thị tên tệp và số dòng khi có exception.

Một số giới hạn thực tế:

- Debugger cần đúng source version tương ứng với class file. Source đã thay đổi sau khi build có thể khiến dòng hiển thị không khớp bytecode.
- Biến chỉ xuất hiện trong phạm vi được ghi nhận; biến ngoài phạm vi hoặc chưa có giá trị không nhất thiết hiển thị.
- Compiler có thể tạo biến synthetic hoặc biến phục vụ triển khai nội bộ; không phải mọi mục trong bytecode đều tương ứng một biến do lập trình viên khai báo.
- JIT có thể tối ưu mã khi chạy. Debugger hiện đại thường phối hợp với JVM để hỗ trợ debug, nhưng giá trị biến ở một số điểm vẫn có thể không khả dụng hoặc khác với cách hình dung từ mã nguồn.
- Khi debug từ xa, cần có source phù hợp trên máy debugger hoặc cấu hình source lookup tương ứng.

## 7. Phân biệt debug information với `-parameters`

`-g` và `-parameters` phục vụ hai mục đích khác nhau và có thể bật độc lập.

| Đặc điểm | `-g` | `-parameters` |
|---|---|---|
| Mục tiêu | Debugger và công cụ phân tích bytecode. | Java Reflection đọc tên tham số method/constructor. |
| Attribute chính | `SourceFile`, `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`. | `MethodParameters`. |
| Cách đọc | Debugger hoặc `javap`. | `Executable.getParameters()` và `Parameter.getName()`. |
| Tác động khi thiếu | Khó đặt breakpoint theo dòng, xem biến và theo dõi source. | Reflection thường không có tên tham số nguồn; `Parameter.isNamePresent()` trả `false`. |
| Tùy chọn compiler | `-g`, `-g:none`, `-g:...`. | `-parameters`. |

`LocalVariableTable` có thể chứa tên tham số dưới dạng thông tin biến trong method, nhưng điều đó không thay thế `MethodParameters`. Java Reflection API dùng `MethodParameters` để xác định tên tham số chính thức.

Có thể kết hợp:

~~~bash
javac --release 17 -g -parameters -d out src/DebugInfoDemo.java
~~~

Cũng có thể tắt debug information nhưng vẫn lưu tên tham số cho reflection:

~~~bash
javac --release 17 -g:none -parameters -d out src/DebugInfoDemo.java
~~~

Trong trường hợp thứ hai, `javap -v` vẫn có thể hiển thị `MethodParameters`, trong khi các attribute debug như `SourceFile`, `LineNumberTable` và `LocalVariableTable` bị bỏ. Nếu framework cần tên tham số lúc runtime, hãy bật `-parameters` cho chính class được framework đọc.

## 8. Phân biệt debug attribute với metadata khác của class file

Không phải mọi attribute trong class file đều là debug information.

- `StackMapTable` chứa stack map frame phục vụ kiểm tra bytecode và xác minh kiểu; nó không phải bảng số dòng hay bảng biến cục bộ.
- `MethodParameters` lưu metadata tên và cờ của tham số method/constructor; nó được điều khiển bởi `-parameters`.
- `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations` lưu annotation theo chính sách retention; chúng phục vụ reflection hoặc công cụ xử lý annotation, không phải debug information.
- `Signature` lưu generic signature của class, field hoặc method; nó không phải `LocalVariableTypeTable`.

Do đó, `javac -g:none` không làm class file mất mọi metadata. Nó bỏ các nhóm debug information do tùy chọn debug kiểm soát; class file vẫn cần các cấu trúc và attribute phục vụ liên kết, kiểm tra và thực thi bytecode.

## 9. Tích hợp debug information với Maven

Với Maven Compiler Plugin, có thể bật debug information bằng cấu hình `debug` và chọn nhóm thông tin qua `debuglevel`.

Ví dụ trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <debug>true</debug>
                <debuglevel>source,lines,vars</debuglevel>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`debug=true` bật sinh debug information; `debuglevel` chọn các nhóm `source`, `lines` và `vars`. Nếu cần kiểm soát chính xác artifact, hãy kiểm tra phiên bản plugin và lệnh compiler thực tế trong log build.

Sau khi build:

~~~bash
mvn clean compile
javap -v -l -classpath target/classes com.example.DebugInfoDemo
~~~

Thay `com.example.DebugInfoDemo` bằng tên lớp đầy đủ trong dự án.

## 10. Tích hợp debug information với Gradle

Trong Gradle Groovy DSL (`build.gradle`):

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.debug = true
    options.debugOptions.debugLevel = "source,lines,vars"
}
~~~

Trong Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.isDebug = true
    options.debugOptions.debugLevel = "source,lines,vars"
}
~~~

Cấu hình này áp dụng cho các task `JavaCompile` phù hợp trong build. Với dự án nhiều module hoặc nhiều source set, cần xác nhận task biên dịch class đang được debug thực sự nhận cấu hình đó.

Có thể kiểm tra class file sau khi build bằng `javap -v -l`. Đừng nhầm việc bật debug cho task test runtime với việc tạo debug information: metadata phải được ghi vào class file trong giai đoạn compile.

## 11. Chọn cấu hình cho phát triển và phát hành

Trong môi trường phát triển, nên giữ thông tin dòng và biến để hỗ trợ breakpoint, stepping và xem biến. `-g` thường là lựa chọn thuận tiện vì ghi đủ ba nhóm thông tin.

Trong môi trường production, quyết định phụ thuộc vào nhu cầu vận hành:

- Nếu cần phân tích stack trace theo số dòng, giữ `source` và `lines`.
- Nếu cần chẩn đoán sâu bằng debugger hoặc công cụ quan sát biến, giữ thêm `vars`.
- Nếu yêu cầu giảm metadata trong artifact, cân nhắc `-g:none` sau khi đánh giá ảnh hưởng tới việc chẩn đoán.
- Nếu framework cần tên tham số reflection, vẫn phải bật `-parameters` độc lập với lựa chọn debug.

Debug information không phải nơi lưu giá trị runtime của biến và không thay thế log, metrics, tracing hoặc core dump. Nó giúp công cụ hiểu vị trí và tên trong bytecode; việc quan sát trạng thái tiến trình còn phụ thuộc JVM, debugger và quyền truy cập lúc chạy.

Class file có thể để lộ tên biến, tên tệp và cấu trúc mã nội bộ. Hãy tránh đặt bí mật, token hoặc dữ liệu nhạy cảm trong tên biến, tên package hay đường dẫn build. Việc bỏ debug information cũng không phải cơ chế bảo vệ mã nguồn; bytecode vẫn có thể được phân tích ngược.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Breakpoint theo dòng không hoạt động như mong đợi | Thiếu `LineNumberTable` hoặc debugger đang dùng source khác phiên bản. | Biên dịch với `-g:lines` hoặc `-g`, xác nhận source đúng build. |
| Stack trace hiển thị `Unknown Source` | Class file thiếu thông tin source/line phù hợp. | Giữ `SourceFile` và `LineNumberTable` khi build artifact cần chẩn đoán. |
| Variables view không có tên biến cục bộ | Class file không có `LocalVariableTable`. | Biên dịch với `-g:vars` hoặc `-g`. |
| Không thấy generic type của biến | Không có `LocalVariableTypeTable` hoặc compiler không ghi generic signature cần thiết. | Dùng `-g:vars`/`-g` và kiểm tra bằng `javap -v -l`. |
| Build local có debug nhưng CI không có | Các task hoặc module dùng cấu hình compiler khác nhau. | Kiểm tra lệnh `javac` thực tế và cấu hình mọi task compile liên quan. |
| `javap` vẫn hiển thị metadata khi dùng `-g:none` | Class file vẫn có các attribute không thuộc nhóm debug, ví dụ `MethodParameters` hoặc `StackMapTable`. | Phân biệt debug attribute với metadata phục vụ reflection và bytecode verification. |
| Debugger hiển thị sai dòng hoặc source | Source file hiện tại không khớp artifact đã build. | Lấy source đúng commit/build và kiểm tra classpath/module path. |
| Đã bật `-g` nhưng Reflection không có tên tham số | Nhầm `LocalVariableTable` với `MethodParameters`. | Bật `-parameters` nếu Reflection cần tên tham số. |

Một quy trình kiểm tra ngắn:

1. Xác định class file thực tế mà ứng dụng đang nạp.
2. Chạy `javap -v -l` trên đúng class file hoặc JAR.
3. Kiểm tra `SourceFile`, `LineNumberTable`, `LocalVariableTable` và `LocalVariableTypeTable`.
4. Kiểm tra tùy chọn `javac` hoặc cấu hình build tool.
5. Xác nhận source code dùng để debug khớp với artifact.
6. Nếu cần tên tham số reflection, kiểm tra riêng `MethodParameters` và `-parameters`.

## 13. Checklist trước khi phát hành

- Đã xác định nhu cầu debug ở môi trường phát triển, kiểm thử và production.
- Dùng `-g` hoặc `-g:source,lines,vars` nếu cần đầy đủ debug information.
- Giữ `SourceFile` và `LineNumberTable` nếu cần stack trace theo số dòng.
- Giữ `LocalVariableTable` và `LocalVariableTypeTable` nếu cần debugger xem biến cục bộ và generic type.
- Không nhầm `-g` với `-parameters`.
- Kiểm tra class file/JAR cuối cùng bằng `javap -v -l`.
- Xác nhận source dùng khi debug đúng phiên bản với artifact.
- Kiểm tra cấu hình Maven/Gradle cho tất cả module và source set cần thiết.
- Không dùng việc bỏ debug information như biện pháp bảo vệ bí mật hoặc thay thế quy trình logging/monitoring.

Debug information giúp kết nối bytecode với mã nguồn để gỡ lỗi hiệu quả. Hãy chọn `-g` hoặc các nhóm `-g:...` theo nhu cầu, xác minh attribute bằng `javap`, và bật `-parameters` riêng nếu framework cần tên tham số qua Reflection.
