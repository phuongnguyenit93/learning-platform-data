# Truyền đối số ứng dụng bằng arg và đối số JVM bằng jvmarg

Khi dùng Apache Ant để chạy một chương trình Java, task `<java>` cần biết hai nhóm thông tin khác nhau: các giá trị mà chương trình nhận trong mảng `String[] args`, và các tùy chọn cấu hình máy ảo Java (JVM) trước khi lớp chính được chạy.

Ant phân biệt hai nhóm này bằng hai phần tử lồng nhau:

- `<arg>` truyền đối số cho ứng dụng Java.
- `<jvmarg>` truyền tùy chọn cho tiến trình JVM được khởi chạy.

Phân biệt đúng hai loại đối số giúp tránh lỗi chương trình không nhận được tham số, JVM không áp dụng heap hoặc system property, và các chuỗi có dấu cách bị tách sai.

## 1. Vị trí của đối số trong lệnh Java

Một lệnh Java chạy từ terminal thường có cấu trúc:

```bash
java [JVM options] -cp [classpath] com.example.Main [application arguments]
```

Ví dụ:

```bash
java -Xms128m -Xmx512m -Dapp.profile=production \
     -cp build/classes com.example.Main \
     --input "data/input file.txt" --verbose
```

Các phần có ý nghĩa khác nhau:

| Thành phần | Ví dụ | Ai sử dụng? |
|---|---|---|
| JVM option | `-Xmx512m` | JVM, để đặt heap tối đa |
| JVM system property | `-Dapp.profile=production` | JVM tạo system property để ứng dụng đọc qua `System.getProperty` |
| Classpath | `-cp build/classes` | JVM/class loader, để tìm class và thư viện |
| Main class | `com.example.Main` | JVM, xác định lớp có phương thức `main` |
| Application argument | `--input`, `data/input file.txt`, `--verbose` | Ứng dụng, nhận trong `String[] args` |

Quy tắc quan trọng: tùy chọn JVM nằm trước tên lớp chính; đối số ứng dụng nằm sau tên lớp chính. Với Ant, `<jvmarg>` tương ứng nhóm tùy chọn JVM, còn `<arg>` tương ứng nhóm đối số ứng dụng.

## 2. Dùng arg để truyền đối số cho ứng dụng

Mỗi phần tử `<arg>` mô tả một đối số của chương trình. Ví dụ:

```xml
<java classname="com.example.Main" fork="true" failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>

    <arg value="--input"/>
    <arg value="data/input.txt"/>
    <arg value="--verbose"/>
</java>
```

Ứng dụng nhận ba phần tử trong `args`:

```java
args[0] = "--input";
args[1] = "data/input.txt";
args[2] = "--verbose";
```

Mỗi `<arg>` tạo một đối số riêng. Nếu ứng dụng cần một cặp tên tùy chọn và giá trị, thường truyền chúng thành hai `<arg>` như ví dụ. Nếu chương trình được thiết kế để nhận một token dạng `--name=value`, có thể truyền cả chuỗi trong một `<arg value="--name=value"/>`.

## 3. Dùng jvmarg để cấu hình JVM

`<jvmarg>` truyền một tùy chọn đến JVM được Ant khởi chạy. Các ví dụ thường gặp:

```xml
<java classname="com.example.Main" fork="true" failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>

    <jvmarg value="-Xms128m"/>
    <jvmarg value="-Xmx512m"/>
    <jvmarg value="-Dapp.profile=production"/>
    <jvmarg value="-Dfile.encoding=UTF-8"/>

    <arg value="--verbose"/>
</java>
```

Ý nghĩa:

- `-Xms128m`: heap ban đầu của JVM là 128 MB.
- `-Xmx512m`: heap tối đa của JVM là 512 MB.
- `-Dapp.profile=production`: đặt system property `app.profile` cho tiến trình Java con.
- `-Dfile.encoding=UTF-8`: truyền system property về encoding mặc định cho tiến trình con; hành vi cụ thể phụ thuộc JDK.

Các tùy chọn như `-Xmx`, `-Xms`, `-D`, `--add-opens` hoặc các tùy chọn GC thuộc về JVM. Chúng không xuất hiện trong `String[] args` của chương trình.

## 4. JVM arguments cần fork tiến trình Java

Task `<java>` có thể chạy lớp chính trong cùng JVM với Ant hoặc khởi chạy một JVM riêng:

- `fork="false"` (mặc định): chạy lớp Java trong JVM đang chạy Ant.
- `fork="true"`: khởi chạy tiến trình JVM riêng cho chương trình.

`<jvmarg>` chỉ có ý nghĩa khi `fork="true"`, vì không thể thay đổi các tùy chọn khởi động của JVM đã chạy Ant. Nếu cần đặt heap, GC, module option hoặc các tùy chọn khởi động khác cho ứng dụng, hãy bật fork.

Ví dụ đúng khi cần cấu hình heap:

```xml
<java classname="com.example.Main" fork="true" failonerror="true">
    <jvmarg value="-Xms256m"/>
    <jvmarg value="-Xmx1g"/>
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
    <arg value="--mode"/>
    <arg value="batch"/>
</java>
```

Nếu bỏ `fork="true"`, các JVM option không thể cấu hình một JVM mới cho lần chạy đó. Khi ứng dụng cần JVM riêng hoặc có tùy chọn khởi động riêng, nên khai báo fork tường minh để người đọc build file hiểu ý định.

## 5. Chuỗi có dấu cách: value giữ nguyên một đối số

Một lỗi phổ biến là cho rằng Ant cần tự thêm dấu nháy kép quanh mọi đối số có dấu cách. Với `<arg value="..."/>`, giá trị được truyền như một đối số duy nhất, kể cả khi chứa dấu cách.

```xml
<java classname="com.example.Main" fork="true">
    <arg value="--message"/>
    <arg value="Hello from Ant build"/>
</java>
```

Ứng dụng nhận:

```java
args[0] = "--message";
args[1] = "Hello from Ant build";
```

Không cần viết thêm dấu nháy kép bên trong `value`. Nếu viết:

```xml
<arg value="&quot;Hello from Ant build&quot;"/>
```

thì dấu nháy có thể trở thành ký tự thực trong đối số ứng dụng, thay vì chỉ là ký hiệu gom nhóm như khi nhập lệnh trong shell.

Ưu tiên `value` khi truyền một đối số riêng lẻ. Cách này rõ ràng, ít phụ thuộc quy tắc phân tích chuỗi và an toàn hơn khi giá trị có dấu cách hoặc ký tự đặc biệt.

## 6. Khác biệt giữa value và line

`<arg>` và `<jvmarg>` hỗ trợ nhiều cách chỉ định nội dung. `value` biểu diễn một đối số riêng. `line` biểu diễn một dòng gồm nhiều token và Ant phân tích dòng đó thành các đối số.

Ví dụ dùng `line`:

```xml
<java classname="com.example.Main" fork="true">
    <arg line="--mode batch --message &quot;Hello from Ant&quot;"/>
</java>
```

Chuỗi `line` được phân tích thành các token; dấu nháy kép trong ví dụ giúp nhóm `Hello from Ant` thành một đối số. Cách này có thể ngắn hơn khi có nhiều token đơn giản, nhưng dễ gây nhầm lẫn khi giá trị chứa dấu nháy, dấu cách hoặc ký tự đặc biệt.

So sánh:

```xml
<!-- Rõ ràng: mỗi phần tử là một đối số. -->
<arg value="--mode"/>
<arg value="batch"/>
<arg value="--message"/>
<arg value="Hello from Ant"/>

<!-- Ngắn hơn nhưng cần chú ý quy tắc phân tích dòng. -->
<arg line="--mode batch --message &quot;Hello from Ant&quot;"/>
```

Với build script cần truyền đường dẫn hoặc chuỗi do người dùng nhập, nên ưu tiên `value`, `file` hoặc `path` tương ứng thay vì ghép một dòng lệnh lớn. Điều này giúp tránh lỗi do quoting và tokenization.

## 7. Truyền đường dẫn bằng file hoặc path

Nếu một đối số là đường dẫn file, Ant hỗ trợ thuộc tính `file` để chuẩn hóa giá trị đường dẫn:

```xml
<java classname="com.example.Main" fork="true">
    <arg value="--input"/>
    <arg file="${basedir}/data/input file.txt"/>
</java>
```

Đối số thứ hai được truyền như một đường dẫn file, kể cả khi tên có dấu cách. Thuộc tính `file` hữu ích khi muốn Ant xử lý đường dẫn theo quy tắc của hệ điều hành hiện tại.

Nếu ứng dụng nhận một danh sách đường dẫn theo cú pháp classpath hoặc path-list của nền tảng, có thể dùng `path`:

```xml
<path id="input.files">
    <pathelement location="data/part-one.csv"/>
    <pathelement location="data/part-two.csv"/>
</path>

<java classname="com.example.ImportTool" fork="true">
    <arg value="--files"/>
    <arg pathref="input.files"/>
</java>
```

`pathref` tham chiếu một path đã khai báo bằng `id`. Ant chuyển path thành chuỗi phân tách theo quy tắc nền tảng. Chỉ dùng cách này nếu ứng dụng hiểu định dạng path-list đó; nếu ứng dụng cần từng file là một đối số riêng, hãy tạo nhiều `<arg file="..."/>`.

## 8. Truyền system property: jvmarg -D hoặc sysproperty

Một system property có thể được truyền bằng JVM option `-D`:

```xml
<jvmarg value="-Dapp.profile=production"/>
```

Trong task `<java>`, Ant còn có nested element `<sysproperty>` chuyên dụng:

```xml
<java classname="com.example.Main" fork="true">
    <sysproperty key="app.profile" value="production"/>
    <sysproperty key="app.config" file="config/production.properties"/>
</java>
```

Hai cách đều phục vụ việc cung cấp system property cho chương trình Java. `<sysproperty>` thường dễ đọc hơn khi chỉ muốn đặt property, còn `<jvmarg>` phù hợp với các tùy chọn JVM thực sự như heap, GC hoặc module flags.

Trong Java, ứng dụng đọc system property bằng:

```java
String profile = System.getProperty("app.profile");
String config = System.getProperty("app.config");
```

System property khác application argument. Property được đọc qua `System.getProperty`; đối số ứng dụng được đọc từ `args` trong phương thức `main`.

## 9. Ví dụ hoàn chỉnh: chạy ứng dụng với cả hai nhóm đối số

Giả sử có ứng dụng:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Profile: " + System.getProperty("app.profile"));
        System.out.println("Max heap: " + Runtime.getRuntime().maxMemory());

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
```

Build file:

```xml
<project name="run-main" default="run" basedir=".">
    <property name="classes.dir" location="${basedir}/build/classes"/>
    <property name="input.file" location="${basedir}/data/input file.txt"/>

    <target name="run" description="Run Main with JVM and application arguments">
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>

            <!-- JVM arguments: applied before the main class starts. -->
            <jvmarg value="-Xms128m"/>
            <jvmarg value="-Xmx512m"/>

            <!-- A system property can also be expressed with sysproperty. -->
            <sysproperty key="app.profile" value="production"/>

            <!-- Application arguments: received in String[] args. -->
            <arg value="--input"/>
            <arg file="${input.file}"/>
            <arg value="--message"/>
            <arg value="Hello from Ant"/>
            <arg value="--verbose"/>
        </java>
    </target>
</project>
```

Khi chạy `ant run`, Ant khởi động JVM con với heap ban đầu 128 MB và tối đa 512 MB. JVM nhận system property `app.profile=production`. Sau khi lớp `Main` bắt đầu chạy, chương trình nhận các đối số `--input`, đường dẫn file, `--message`, chuỗi `Hello from Ant` và `--verbose` trong `args`.

## 10. So sánh trực tiếp arg và jvmarg

| Tiêu chí | `<arg>` | `<jvmarg>` |
|---|---|---|
| Đối tượng nhận | Ứng dụng Java | JVM được khởi chạy |
| Vị trí tương đương trong lệnh | Sau tên main class hoặc sau `-jar` | Trước tên main class hoặc `-jar` |
| Ví dụ | `--input`, `report.csv`, `--verbose` | `-Xmx1g`, `-Xms256m`, `-Dname=value` |
| Java đọc ở đâu? | Mảng `String[] args` | JVM option; `-D` tạo system property |
| Có cần fork? | Không bắt buộc | Có, để cấu hình JVM con |
| Dùng cho dữ liệu nghiệp vụ? | Có | Không nên |
| Dùng cho heap/GC/module flags? | Không | Có |

Một cách nhớ đơn giản: nếu giá trị cần được xử lý trong `main(String[] args)`, dùng `<arg>`. Nếu giá trị thay đổi cách JVM khởi động hoặc vận hành, dùng `<jvmarg>` và bật `fork="true"`.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `args` không nhận được `-Xmx512m` | Đã truyền tùy chọn JVM bằng `<arg>` | Chuyển sang `<jvmarg>` và bật fork |
| JVM không áp dụng `--add-opens` hoặc `-Xmx` | Dùng `<jvmarg>` nhưng không fork tiến trình | Đặt `fork="true"` |
| Ứng dụng nhận chuỗi có dấu nháy không mong muốn | Tự thêm dấu nháy vào `value` | Dùng một `<arg value="..."/>` cho mỗi đối số; không thêm quote để gom nhóm |
| Một đường dẫn có dấu cách bị tách thành nhiều phần | Ghép chuỗi bằng `line` không đúng cách | Dùng `<arg file="..."/>` hoặc `<arg value="..."/>` |
| Ứng dụng không đọc được system property | Đặt property thành application argument | Dùng `-D` trong `<jvmarg>` hoặc `<sysproperty>` |
| Không tìm thấy lớp chính | Classpath thiếu thư mục class hoặc JAR | Kiểm tra nested `<classpath>` và artifact đã compile |
| Build vẫn thành công dù ứng dụng thoát lỗi | Chưa bật `failonerror` | Dùng `failonerror="true"` nếu mã thoát khác 0 phải làm build thất bại |
| Tham số bị lẫn giữa JVM và ứng dụng | Không phân biệt vị trí trước/sau main class | Nhóm `<jvmarg>` và `<arg>` riêng, ghi chú trong build file |

Khi debug, có thể bật log chi tiết của Ant:

```bash
ant -verbose run
```

Log giúp quan sát lệnh được Ant dựng và quá trình chạy task. Không nên in các tham số chứa mật khẩu hoặc token ra log; hãy cấp secret bằng cơ chế an toàn và tránh đưa chúng vào `echo` hoặc thông báo lỗi.

## 12. Bài tập thực hành

1. Tạo lớp `com.example.ArgsPrinter` in từng phần tử của `String[] args`.
2. Dùng `<arg>` truyền `--name`, `Java Learner` và `--verbose`; xác nhận chuỗi có dấu cách là một đối số duy nhất.
3. Dùng `<jvmarg value="-Xmx256m"/>` và `fork="true"`; in `Runtime.getRuntime().maxMemory()` để quan sát heap tối đa.
4. Truyền `-Dapp.profile=test` bằng `<jvmarg>` rồi đọc bằng `System.getProperty("app.profile")`.
5. Thay `-Dapp.profile=test` bằng `<sysproperty key="app.profile" value="test"/>` và so sánh cách khai báo.
6. Truyền đường dẫn có dấu cách bằng `<arg file="..."/>`.
7. Thử bỏ `fork="true"` trong ví dụ có `<jvmarg>` và quan sát giới hạn của JVM option.
8. Đặt `failonerror="true"`, cho ứng dụng thoát với mã khác 0 và xác nhận Ant báo build thất bại.

Sau bài tập, người học cần giải thích được vì sao heap phải truyền qua `jvmarg`, vì sao tùy chọn ứng dụng phải truyền qua `arg`, cách Ant giữ nguyên đối số có dấu cách và khi nào nên dùng `<sysproperty>`.

## 13. Nguyên tắc sử dụng trong build thực tế

Hãy nhóm đối số theo đúng nơi tiêu thụ: JVM flags trong `<jvmarg>`, tham số nghiệp vụ trong `<arg>`, system property trong `<sysproperty>` khi phù hợp, và classpath trong `<classpath>`. Ưu tiên mỗi `<arg>` cho một giá trị rõ ràng thay vì ghép dòng lệnh dài. Bật `fork="true"` khi cần JVM riêng hoặc cần tùy chỉnh tùy chọn khởi động.

Việc phân chia rõ ràng giúp build script thể hiện chính xác hợp đồng giữa Ant, JVM và ứng dụng Java. Khi có lỗi, người đọc biết nên kiểm tra cấu hình JVM, classpath hay cách chương trình phân tích `args`.
