# Chọn mức ngôn ngữ, bytecode bằng `source`, `target` và `release`

Khi biên dịch một dự án Java bằng Apache Ant, bạn cần quyết định mã nguồn được phép sử dụng những tính năng ngôn ngữ nào và tệp `.class` tạo ra có thể chạy trên phiên bản Java nào. Đây là hai yêu cầu liên quan nhưng không giống nhau.

Task `<javac>` của Ant cung cấp các thuộc tính `source`, `target` và `release` để cấu hình mức tương thích khi biên dịch:

- `source` chọn mức ngôn ngữ Java mà trình biên dịch chấp nhận.
- `target` chọn định dạng bytecode (class file) được tạo ra.
- `release` chọn một phiên bản Java SE đích và đồng thời giới hạn API nền tảng được phép sử dụng.

Với JDK 9 trở lên, `--release` thường là lựa chọn phù hợp nhất khi cần biên dịch cho một phiên bản Java cũ hơn JDK đang dùng. Nếu chỉ đặt `source` và `target`, mã nguồn có thể vô tình sử dụng API chỉ tồn tại trong JDK mới, dẫn đến lỗi khi chạy trên Java cũ.

Sau bài học, bạn có thể:

- Phân biệt mức ngôn ngữ, định dạng bytecode và API nền tảng.
- Cấu hình `source` và `target` trong task `<javac>`.
- Dùng `release` để biên dịch cho một phiên bản Java cụ thể.
- Hiểu giới hạn của `source`/`target` khi biên dịch bằng JDK mới.
- Chọn cấu hình tương thích phù hợp với JDK và Ant của dự án.
- Nhận biết lỗi class file version không tương thích khi chạy ứng dụng.

## 1. Ba khái niệm cần phân biệt

Để chọn đúng cấu hình, hãy tách ba câu hỏi:

1. **Mã nguồn được phép viết theo cú pháp và tính năng ngôn ngữ nào?** Đây là vai trò của `source`.
2. **Trình biên dịch tạo ra bytecode theo định dạng của phiên bản Java nào?** Đây là vai trò của `target`.
3. **Mã nguồn được phép tham chiếu những API Java SE nào?** Đây là phần mà `release` kiểm soát cùng với mức ngôn ngữ và bytecode.

Ví dụ, bạn có thể dùng JDK 17 để biên dịch một ứng dụng cần chạy trên Java 11. Mục tiêu không chỉ là tạo class file mà JVM Java 11 đọc được; mã nguồn còn phải tránh gọi API chỉ có từ Java 17 trở lên.

### 1.1. `source`: mức ngôn ngữ

Tùy chọn `-source` của `javac` xác định phiên bản ngôn ngữ Java mà trình biên dịch dùng để kiểm tra mã nguồn. Nó ảnh hưởng đến cú pháp và tính năng ngôn ngữ được chấp nhận.

Ví dụ, khi đặt mức ngôn ngữ Java 8, mã nguồn không thể dùng cú pháp chỉ được giới thiệu ở các phiên bản Java sau đó.

Trong Ant:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="1.8"
       includeantruntime="false" />
```

Thuộc tính `source` được truyền đến trình biên dịch tương ứng với tùy chọn mức ngôn ngữ. Giá trị phải được JDK đang sử dụng hỗ trợ.

`source` không tự bảo đảm chương trình chạy được trên phiên bản Java tương ứng. Nó chủ yếu giới hạn ngôn ngữ được chấp nhận khi biên dịch.

### 1.2. `target`: định dạng bytecode

Tùy chọn `-target` yêu cầu `javac` tạo tệp class theo định dạng của một phiên bản Java đích. JVM đọc định dạng class file để nạp và thực thi lớp.

Trong Ant:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="1.8"
       target="1.8"
       includeantruntime="false" />
```

Ở đây, `target="1.8"` yêu cầu tạo bytecode theo định dạng Java 8. JVM Java 8 có thể đọc định dạng này, trong khi một JVM cũ hơn không nhất thiết hỗ trợ.

`target` không tự giới hạn API mà mã nguồn được phép gọi. Nếu dùng JDK mới và chỉ đặt `source="1.8"`, `target="1.8"`, mã nguồn vẫn có nguy cơ tham chiếu API được bổ sung sau Java 8. Khi chạy trên Java 8, lớp có thể nạp được nhưng thất bại khi gọi API không tồn tại.

### 1.3. `release`: mức phát hành Java đầy đủ

Tùy chọn `--release` của `javac` được giới thiệu từ JDK 9. Nó kết hợp các ràng buộc cần thiết để biên dịch cho một phiên bản Java SE được hỗ trợ:

- Mức ngôn ngữ tương ứng với phiên bản đích.
- Định dạng bytecode tương ứng với phiên bản đích.
- Bộ API Java SE công khai của phiên bản đích.

Trong Ant, dùng thuộc tính `release` của task `<javac>` khi phiên bản Ant và trình biên dịch hỗ trợ:

```xml
<javac srcdir="src"
       destdir="build/classes"
       release="11"
       encoding="UTF-8"
       includeantruntime="false" />
```

Lệnh tương đương về ý nghĩa là:

```bash
javac --release 11 -d build/classes src/Main.java
```

Với cấu hình này, JDK mới sẽ từ chối mã nguồn gọi API Java SE chỉ xuất hiện sau Java 11, thay vì chỉ tạo bytecode cũ nhưng vẫn tham chiếu API mới.

`release` là cách diễn đạt mục tiêu tương thích rõ ràng hơn khi build bằng JDK 9 trở lên. Không kết hợp `release` với `source` hoặc `target` trong cùng lần gọi `javac`; các tùy chọn này đại diện cho những cách chỉ định mức biên dịch khác nhau và `javac` không cho phép dùng chung với `--release`.

## 2. So sánh `source`, `target` và `release`

| Thuộc tính Ant | Tùy chọn `javac` | Kiểm soát | Giới hạn chính |
|---|---|---|---|
| `source` | `-source` | Cú pháp và tính năng ngôn ngữ được chấp nhận. | Không quyết định đầy đủ API nền tảng hoặc định dạng bytecode đích. |
| `target` | `-target` | Định dạng bytecode/class file được tạo. | Không tự giới hạn API nền tảng có thể được tham chiếu. |
| `release` | `--release` | Mức ngôn ngữ, bytecode và API Java SE của phiên bản đích. | Cần JDK 9 trở lên và phiên bản đích phải nằm trong phạm vi JDK hỗ trợ. |

Có thể ghi nhớ bằng cách đặt ba câu hỏi:

```text
source  -> Được viết bằng ngôn ngữ Java mức nào?
target  -> Tạo class file theo định dạng nào?
release -> Biên dịch như một bản phát hành Java cụ thể nào?
```

## 3. Vì sao chỉ đặt `source` và `target` có thể chưa đủ?

Giả sử bạn dùng JDK 17 để biên dịch chương trình cần chạy trên Java 11:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="11"
       target="11"
       includeantruntime="false" />
```

Hai thuộc tính trên giới hạn mức ngôn ngữ và định dạng bytecode. Tuy nhiên, trình biên dịch vẫn nhìn thấy thư viện nền tảng của JDK 17. Nếu mã nguồn gọi một phương thức chỉ được bổ sung trong Java 17, trình biên dịch có thể chấp nhận lời gọi đó trong khi vẫn tạo class file theo định dạng Java 11.

Khi chạy trên Java 11, JVM có thể nạp class file nhưng không tìm thấy phương thức hoặc lớp mới được sử dụng. Tùy thời điểm liên kết, ứng dụng có thể gặp lỗi như `NoSuchMethodError` hoặc `NoClassDefFoundError`.

Ví dụ minh họa vấn đề:

```java
public class Example {
    public static void main(String[] args) {
        // Giả sử API được gọi chỉ có từ một JDK mới hơn phiên bản chạy mục tiêu.
        // source/target cũ không tự động loại API mới khỏi thư viện JDK đang dùng.
    }
}
```

Không cần ghi nhớ một API cụ thể để hiểu vấn đề. Điều cần nhớ là bytecode tương thích không đồng nghĩa với API tương thích.

### 3.1. `--release` giải quyết vấn đề API như thế nào?

Với JDK 17, thay cấu hình `source`/`target` bằng `release`:

```xml
<javac srcdir="src"
       destdir="build/classes"
       release="11"
       includeantruntime="false" />
```

Lúc này, trình biên dịch sử dụng tập API Java SE dành cho Java 11. Nếu mã nguồn tham chiếu API chỉ có trong Java 17, quá trình biên dịch báo lỗi. Nhờ vậy, lỗi tương thích API được phát hiện ngay trong bước build thay vì chờ đến khi chạy trên JVM cũ.

`--release` áp dụng cho API nền tảng Java SE. Nó không tự kiểm tra mọi thư viện bên thứ ba. Nếu dự án dùng một thư viện ngoài, bạn vẫn phải chọn phiên bản thư viện tương thích với Java đích và cấu hình dependency phù hợp.

## 4. Bytecode và khả năng tương thích JVM

Tệp `.class` có cấu trúc định dạng và một số phiên bản được biểu diễn bằng số major version. JVM dùng thông tin này để xác định có hỗ trợ class file hay không.

Một số giá trị thường gặp:

| Phiên bản Java | Major version của class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

JVM của phiên bản Java mới thường đọc được class file của phiên bản cũ hơn, trong phạm vi tương thích mà JVM hỗ trợ. JVM cũ không đọc được class file được tạo cho một phiên bản mới hơn.

Ví dụ, nếu lớp được biên dịch thành class file Java 17 rồi chạy bằng Java 11, JVM Java 11 có thể báo lỗi:

```text
java.lang.UnsupportedClassVersionError
```

Thông báo thường cho biết class file có phiên bản mới hơn phiên bản mà runtime hỗ trợ.

### 4.1. Class file version không phải phiên bản JDK cài đặt

JDK dùng để biên dịch và JVM dùng để chạy có thể là hai phiên bản khác nhau. Ví dụ:

```text
Máy build: JDK 17
Mức biên dịch: Java 11
Máy chạy: JVM 11
```

Đây là tình huống hợp lệ nếu chương trình và tất cả thư viện phụ thuộc tương thích Java 11. Dùng JDK mới để build không bắt buộc sản phẩm phải yêu cầu đúng phiên bản JDK đó, miễn là mức biên dịch và API được giới hạn đúng.

### 4.2. Kiểm tra class file version

Công cụ `javap` có thể hiển thị thông tin phiên bản class file:

```bash
javap -verbose build/classes/com/example/Main.class
```

Trong kết quả, tìm dòng `major version`. Ví dụ `major version: 55` tương ứng với định dạng class file Java 11.

Bạn cũng có thể kiểm tra phiên bản runtime:

```bash
java -version
```

Nếu ứng dụng báo `UnsupportedClassVersionError`, hãy so sánh major version của lớp với khả năng hỗ trợ của JVM đang chạy.

## 5. Cấu hình `source` và `target` trong Ant

Với JDK chưa hỗ trợ `--release`, hoặc khi cần kiểm soát riêng mức ngôn ngữ và bytecode, có thể dùng `source` và `target`:

```xml
<project name="source-target-demo" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="classes.dir" location="build/classes" />

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               source="1.8"
               target="1.8"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>
</project>
```

Khi chạy `ant compile`, Ant gọi trình biên dịch với mức ngôn ngữ Java 8 và định dạng bytecode Java 8.

### 5.1. Nên đặt `source` và `target` cùng mức

Trong đa số dự án, hai giá trị nên giống nhau:

```xml
<javac source="11" target="11" ... />
```

Nếu đặt `source` cao hơn `target`, bạn có thể cho phép cú pháp hoặc tính năng ngôn ngữ mà định dạng bytecode đích không thể biểu diễn. `javac` có các giới hạn riêng về cặp phiên bản hợp lệ và có thể từ chối cấu hình không hỗ trợ.

Nếu đặt `source` thấp hơn `target`, buildfile có thể tạo bytecode mới hơn mức ngôn ngữ cần thiết, làm giảm khả năng chạy trên các JVM cũ. Trừ khi có lý do đặc biệt, hãy giữ hai giá trị bằng nhau hoặc dùng `release`.

### 5.2. Giới hạn API khi dùng JDK cũ

Khi dùng `source` và `target` để biên dịch cho nền tảng cũ hơn JDK hiện tại, cần bảo đảm trình biên dịch tham chiếu đúng API của nền tảng đích. Nếu chỉ dùng thư viện của JDK đang cài, mã nguồn vẫn có thể gọi API mới.

Trước JDK 9, cách xử lý thường là dùng `bootclasspath` trỏ đến thư viện nền tảng của JDK đích, khi bộ JDK đó cung cấp thư viện phù hợp. Ví dụ khái quát:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="7"
       target="7"
       bootclasspath="${java7.home}/jre/lib/rt.jar"
       includeantruntime="false" />
```

Đường dẫn `rt.jar` chỉ phù hợp với các JDK cũ có cấu trúc đó. Từ JDK 9, hệ thống module thay đổi cách tổ chức thư viện nền tảng và không còn `rt.jar` theo cách cũ. Với JDK 9 trở lên, ưu tiên `release` thay cho việc tự cấu hình bootclasspath để mô phỏng API nền tảng.

## 6. Dùng `release` trong task `<javac>`

Nếu máy build dùng JDK 9 trở lên và phiên bản Ant hỗ trợ thuộc tính `release`, đây thường là cấu hình nên chọn:

```xml
<project name="release-demo" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="classes.dir" location="build/classes" />
    <property name="java.release" value="17" />

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>
</project>
```

Ở đây, property `java.release` cho phép thay đổi phiên bản Java mục tiêu tại một nơi. Có thể truyền mức khác khi chạy:

```bash
ant -Djava.release=11 compile
```

Buildfile sẽ yêu cầu trình biên dịch biên dịch cho Java 11. Phiên bản đích phải nằm trong phạm vi `--release` mà JDK đang dùng hỗ trợ.

### 6.1. Yêu cầu phiên bản Ant và JDK

`--release` là tùy chọn của `javac` từ JDK 9. Thuộc tính `release` của task `<javac>` có trong các phiên bản Ant hỗ trợ tính năng này (Ant 1.9.8 trở lên). Nếu Ant quá cũ, nó có thể không nhận ra thuộc tính `release`.

Kiểm tra phiên bản công cụ:

```bash
ant -version
javac -version
```

Nếu cần `release` nhưng Ant đang dùng chưa hỗ trợ thuộc tính này, hãy nâng cấp Ant. Một cách khác là cấu hình compiler argument phù hợp, nhưng chỉ dùng khi hiểu rõ compiler adapter và cách Ant chuyển các đối số cho `javac`.

### 6.2. Không trộn `release` với `source`/`target`

Không viết cấu hình như sau:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="11"
       target="11"
       release="11" />
```

`javac` không cho phép kết hợp `--release` với `-source` hoặc `-target`. Hãy chọn một trong hai cách:

```xml
<!-- Cách 1: JDK 9+ và Ant hỗ trợ release -->
<javac srcdir="src" destdir="build/classes" release="11" />
```

```xml
<!-- Cách 2: dùng source và target -->
<javac srcdir="src" destdir="build/classes" source="11" target="11" />
```

Với JDK 9 trở lên, cách thứ nhất thường bảo đảm mục tiêu tương thích API tốt hơn.

## 7. Chọn cấu hình theo môi trường build

Không phải dự án nào cũng dùng cùng một phiên bản JDK hoặc Ant. Hãy chọn cấu hình dựa trên công cụ có sẵn và phiên bản Java thấp nhất mà ứng dụng cần hỗ trợ.

| Môi trường biên dịch | Cách cấu hình phù hợp | Ghi chú |
|---|---|---|
| JDK 8, build cho Java 8 | `source="1.8" target="1.8"`. | JDK 8 chỉ có API Java 8 nên không có API mới hơn để vô tình gọi. |
| JDK 8, build cho Java cũ hơn | `source` + `target` và bootclasspath của JDK đích. | Cần đúng thư viện nền tảng của phiên bản Java đích. |
| JDK 11/17/21, build cho phiên bản Java được hỗ trợ | `release="N"`. | Giới hạn ngôn ngữ, bytecode và API Java SE. |
| JDK mới, Ant chưa hỗ trợ thuộc tính `release` | Nâng cấp Ant hoặc cấu hình compiler argument có kiểm soát. | Không giả định Ant cũ hiểu thuộc tính mới. |

### 7.1. Dự án chỉ hỗ trợ một phiên bản Java

Nếu ứng dụng chỉ hỗ trợ Java 17, có thể đặt `release="17"` làm mặc định trong buildfile:

```xml
<property name="java.release" value="17" />
```

Sau đó tất cả target biên dịch dùng chung property này. Điều đó giúp các module tránh vô tình dùng mức Java khác nhau.

### 7.2. Dự án cần hỗ trợ nhiều phiên bản Java

Nếu phát hành nhiều biến thể cho các runtime khác nhau, hãy tạo cấu hình build riêng hoặc truyền property đích cho từng lần build. Ví dụ:

```bash
ant -Djava.release=11 compile
ant -Djava.release=17 compile
```

Mỗi lần build nên ghi sản phẩm vào thư mục đầu ra riêng nếu hai biến thể cần tồn tại đồng thời:

```xml
<property name="build.dir" value="build" />
<property name="classes.dir" value="${build.dir}/java-${java.release}/classes" />
```

Nếu dùng cùng một thư mục class output cho nhiều release, các tệp được tạo từ lần trước có thể còn sót và gây nhầm lẫn. Hãy dọn hoặc phân tách đầu ra theo phiên bản.

## 8. Kiểm tra và xử lý lỗi tương thích

### 8.1. `UnsupportedClassVersionError`

Lỗi này thường xảy ra khi JVM chạy cũ hơn định dạng class file mà chương trình yêu cầu.

Ví dụ thông báo:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
```

Cách xử lý:

1. Xác định JVM thực tế đang chạy bằng `java -version`.
2. Kiểm tra class file bằng `javap -verbose`.
3. Hạ mức `release` xuống phiên bản runtime cần hỗ trợ, nếu JDK hiện tại hỗ trợ mức đó.
4. Hoặc nâng cấp runtime nếu ứng dụng được phép yêu cầu Java mới hơn.
5. Biên dịch lại toàn bộ module và kiểm tra cả thư viện phụ thuộc.

### 8.2. `NoSuchMethodError` hoặc `NoClassDefFoundError`

Các lỗi này có thể xảy ra khi class file được JVM nạp nhưng mã chạy tham chiếu một API hoặc lớp không có trong runtime thực tế. Một nguyên nhân phổ biến là dùng `source`/`target` cũ nhưng biên dịch trên JDK mới mà không giới hạn API.

Cách xử lý:

- Dùng `release` khi có thể.
- Kiểm tra thư viện bên thứ ba có tương thích với Java mục tiêu không.
- Kiểm tra classpath và phiên bản dependency thực tế khi chạy.
- Tránh trộn các JAR được biên dịch cho nhiều mức Java không tương thích.

### 8.3. Trình biên dịch không hỗ trợ mức được yêu cầu

Nếu JDK đang dùng quá cũ, `javac` có thể báo không hỗ trợ `source`, `target` hoặc `release` được yêu cầu. Hãy kiểm tra `javac -version` và danh sách mức được hỗ trợ của chính trình biên dịch.

Không phải JDK nào cũng có thể tạo bytecode cho mọi phiên bản Java cũ. Ví dụ, một JDK mới có thể đã loại bỏ khả năng tạo class file cho các phiên bản rất cũ. Khi mức đích nằm ngoài phạm vi hỗ trợ, cần dùng JDK phù hợp hoặc thay đổi yêu cầu runtime.

### 8.4. Ant và javac không cùng một JDK

Trong một số môi trường, Ant được khởi chạy bằng một JRE/JDK, còn compiler được chọn qua cấu hình khác hoặc được gọi ở tiến trình riêng. Khi kết quả không như mong đợi, kiểm tra:

```bash
ant -version
java -version
javac -version
```

Trên Windows, có thể xem đường dẫn các chương trình:

```powershell
where.exe java
where.exe javac
```

Trên macOS/Linux:

```bash
which java
which javac
```

Đảm bảo Ant đang sử dụng JDK dự kiến, và không nhầm phiên bản `java` trên `PATH` với compiler mà task thực sự gọi.

## 9. Ví dụ buildfile hoàn chỉnh

Ví dụ sau dùng JDK 17 để biên dịch dự án cho Java 11. Mã nguồn và kết quả được đặt trong các thư mục riêng:

```xml
<project name="java-release-demo" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="java.release" value="11" />
    <property name="classes.dir" location="${build.dir}/java-${java.release}/classes" />

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false"
               debug="true" />
    </target>
</project>
```

Chạy:

```bash
ant clean compile
```

Hoặc biên dịch cho một mức khác được JDK hỗ trợ:

```bash
ant -Djava.release=17 clean compile
```

Với cấu hình này, đầu ra được đặt theo mức Java:

```text
build/
└── java-11/
    └── classes/
        └── ... các tệp .class ...
```

Khi đổi sang Java 17, đầu ra nằm trong `build/java-17/classes`, tránh trộn class file của hai mức phát hành.

## 10. Bài thực hành

Tạo một dự án Java nhỏ:

```text
java-release-lab/
├── build.xml
└── src/
    └── Hello.java
```

Tệp `src/Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
```

Thực hiện các bước:

1. Kiểm tra `ant -version`, `java -version` và `javac -version`.
2. Tạo target `compile` dùng `javac` với `source="1.8"` và `target="1.8"`.
3. Nếu dùng JDK 9 trở lên và Ant hỗ trợ, đổi cấu hình sang `release="8"`.
4. Biên dịch chương trình và dùng `javap -verbose` để xem major version của `Hello.class`.
5. Chạy chương trình bằng runtime Java 8 nếu môi trường có sẵn runtime đó.
6. Đổi `release` sang một mức Java cao hơn, biên dịch lại vào thư mục riêng và so sánh class file.
7. Thử đặt `release` cùng `source`/`target`, quan sát lỗi của compiler rồi giải thích vì sao phải chọn một cách cấu hình.

Buildfile gợi ý:

```xml
<project name="java-release-lab" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="java.release" value="8" />
    <property name="classes.dir" location="${build.dir}/java-${java.release}" />

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>
</project>
```

Nếu môi trường không có JDK 9 trở lên hoặc Ant chưa hỗ trợ thuộc tính `release`, hãy thực hành bằng `source`/`target` và ghi rõ giới hạn API của cách cấu hình đó.

### Câu hỏi tự kiểm tra

1. `source` kiểm soát điều gì trong quá trình biên dịch?
2. `target` ảnh hưởng đến phần nào của tệp `.class`?
3. Vì sao `source="1.8" target="1.8"` khi biên dịch bằng JDK 17 vẫn có thể tạo mã gọi API không tồn tại trên Java 8?
4. `release="8"` khác gì so với cặp `source="1.8" target="1.8"`?
5. Có thể dùng `release` cùng lúc với `source` và `target` không?
6. Vì sao JVM cũ có thể báo `UnsupportedClassVersionError`?
7. Nếu gặp `NoSuchMethodError` trên runtime cũ, ngoài bytecode version cần kiểm tra điều gì?
8. Khi build cho nhiều phiên bản Java, vì sao nên tách thư mục class output?

### Đáp án gợi ý

- `source` xác định mức cú pháp và tính năng ngôn ngữ Java được chấp nhận.
- `target` xác định định dạng bytecode/class file được tạo ra.
- Vì `source`/`target` không tự giới hạn API nền tảng mà JDK mới cung cấp cho trình biên dịch.
- `release` giới hạn đồng thời ngôn ngữ, bytecode và API Java SE của phiên bản đích.
- Không. `javac` không cho phép kết hợp `--release` với `-source` hoặc `-target`.
- Vì class file được biên dịch cho phiên bản mới hơn định dạng mà JVM cũ hỗ trợ.
- Cần kiểm tra API Java SE, thư viện bên thứ ba, classpath và phiên bản dependency khi chạy.
- Để tránh trộn class file của nhiều mức bytecode và bảo đảm kết quả build rõ ràng.

## Kết luận

`source` chọn mức ngôn ngữ, `target` chọn định dạng bytecode và `release` kết hợp cả hai với API Java SE của phiên bản đích. Khi dùng JDK 9 trở lên, hãy ưu tiên `release` nếu cần tạo ứng dụng tương thích với một phiên bản Java cũ hơn. Nếu dùng `source`/`target`, hãy nhớ rằng bytecode cũ chưa đủ để bảo đảm API tương thích. Cấu hình đúng mức Java trong task `<javac>`, kiểm tra phiên bản JDK/Ant và tách thư mục đầu ra khi build nhiều release sẽ giúp phát hiện lỗi tương thích ngay trong quá trình build.
