# Tùy chọn source và target trong javac

Khi biên dịch Java bằng JDK mới nhưng cần chạy chương trình trên một phiên bản Java cũ hơn, cần kiểm soát cả cú pháp ngôn ngữ, định dạng bytecode và những API nền tảng được phép sử dụng. Hai tùy chọn **--source** và **--target** điều khiển hai phần khác nhau của quá trình này. Từ Java 9, tùy chọn **--release** cung cấp cách cấu hình tương thích đầy đủ hơn trong phần lớn trường hợp.

Bài này sử dụng cú pháp của **javac** trong JDK 17 trở lên, giải thích ý nghĩa từng tùy chọn, cách kiểm tra kết quả biên dịch và những lỗi tương thích thường gặp.

## 1. Ba khái niệm cần phân biệt

### 1.1. Source level: phiên bản cú pháp Java

Source level xác định phiên bản ngôn ngữ Java mà trình biên dịch chấp nhận. Nó quyết định chương trình có thể sử dụng những cú pháp và tính năng ngôn ngữ nào.

Ví dụ, một chương trình dùng cú pháp **var** chỉ hợp lệ từ Java 10 trở lên. Nếu biên dịch với source level 8, trình biên dịch sẽ báo lỗi cú pháp dù đang chạy trên JDK 17.

Tùy chọn điều khiển source level là **--source N**.

### 1.2. Target level: phiên bản bytecode

Target level xác định định dạng class file mà **javac** sinh ra. JVM chỉ chạy được class file có phiên bản mà runtime hỗ trợ.

Ví dụ, class file Java 11 có major version 55; class file Java 17 có major version 61. Nếu chương trình được biên dịch thành class file mới hơn runtime đang chạy hỗ trợ, JVM có thể báo **UnsupportedClassVersionError**.

Tùy chọn điều khiển target level là **--target N**.

### 1.3. Platform API: API có sẵn ở runtime mục tiêu

Ngoài cú pháp và bytecode, chương trình còn gọi các lớp và phương thức của Java Platform API, ví dụ **java.lang.String**, **java.util.List** hoặc **java.nio.file.Path**.

Một JDK mới có thể biết những API chưa tồn tại trong runtime cũ. Nếu chỉ đặt **--source** và **--target**, trình biên dịch vẫn có thể nhìn thấy API của JDK đang dùng. Kết quả là bytecode có phiên bản cũ nhưng lại gọi một phương thức mới mà runtime mục tiêu không có.

Đây là lý do cần hiểu khác biệt giữa **--source**/**--target** và **--release**.

## 2. Dùng --source và --target

Cú pháp:

~~~text
javac --source <release> --target <release> [other-options] source-files
~~~

- **--source** chọn quy tắc cú pháp và tính năng ngôn ngữ của phiên bản Java chỉ định.
- **--target** chọn phiên bản class file được sinh ra.
- Hai giá trị thường được đặt bằng nhau để tránh tạo ra sự kết hợp khó hiểu giữa cú pháp mới và bytecode cũ.

Ví dụ biên dịch mã theo cú pháp Java 11 và tạo class file tương thích với Java 11:

~~~powershell
javac --source 11 --target 11 -d out src/com/example/App.java
~~~

Có thể dùng dạng viết tắt **-source** và **-target**:

~~~powershell
javac -source 11 -target 11 -d out src/com/example/App.java
~~~

Tên dài có hai dấu gạch ngang dễ đọc hơn và thường được ưu tiên trong script mới.

### 2.1. Vì sao hai tùy chọn này chưa đủ để đảm bảo tương thích?

**--source 11** yêu cầu cú pháp Java 11, còn **--target 11** tạo class file theo định dạng Java 11. Nhưng nếu dùng JDK 17, trình biên dịch vẫn có thể truy cập các API nền tảng của Java 17 khi biên dịch, trừ khi môi trường API được giới hạn riêng.

Ví dụ sau dùng phương thức **String.isBlank()**, được bổ sung từ Java 11:

~~~java
public class ApiExample {
    public static void main(String[] args) {
        System.out.println("   ".isBlank());
    }
}
~~~

Nếu dùng JDK 17 để biên dịch với **--source 8 --target 8**, mã có thể được chấp nhận vì cú pháp vẫn hợp lệ và API Java 17 có phương thức đó. Class file được tạo theo target 8, nhưng khi chạy trên Java 8, lớp **String** không có **isBlank()**. Chương trình có thể thất bại lúc liên kết hoặc gọi phương thức, thường biểu hiện bằng **NoSuchMethodError**.

Ngoài ra, khi dùng **--source** và **--target** cũ hơn JDK đang chạy, **javac** có thể cảnh báo rằng system modules path chưa được đặt cùng source level. Cảnh báo này nhắc rằng trình biên dịch không tự động giới hạn API nền tảng về phiên bản cũ.

## 3. Dùng --release để biên dịch tương thích

**--release N** là tùy chọn được khuyến nghị khi cần biên dịch cho một phiên bản Java cũ hơn bằng JDK mới.

Nó kết hợp ba yêu cầu:

1. Dùng source level của phiên bản chỉ định.
2. Sinh class file theo target level của phiên bản đó.
3. Giới hạn API Java Platform ở những API được công bố cho phiên bản đó.

Ví dụ, biên dịch mã cho Java 11 bằng JDK 17:

~~~powershell
javac --release 11 -d out src/com/example/App.java
~~~

Nếu mã gọi API chỉ xuất hiện từ Java 12 trở đi, trình biên dịch sẽ báo lỗi khi biên dịch với **--release 11** thay vì tạo bytecode có nguy cơ gọi API không tồn tại trên Java 11.

Có thể dùng các phiên bản phát hành khác mà JDK hiện tại hỗ trợ:

~~~powershell
javac --release 8 -d out src/com/example/App.java
javac --release 11 -d out src/com/example/App.java
javac --release 17 -d out src/com/example/App.java
~~~

Danh sách release được hỗ trợ phụ thuộc phiên bản JDK của trình biên dịch. Hãy kiểm tra bằng:

~~~powershell
javac --help
~~~

Với JDK 17, **--release** chỉ nhận các release mà bản **javac** đó hỗ trợ; không thể dùng JDK 17 để tạo target Java 21. Muốn biên dịch cho một release mới hơn, cần dùng JDK tương ứng hoặc mới hơn.

Không kết hợp **--release** với **--source** hoặc **--target** trong cùng lệnh. **--release** đã thiết lập cả ba khía cạnh tương thích nói trên.

## 4. Ví dụ thực hành với Java 11

Tạo cấu trúc:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── App.java
└── out/
~~~

Nội dung **src/com/example/App.java**:

~~~java
package com.example;

public class App {
    public static void main(String[] args) {
        String message = "  Java 11  ".strip();
        System.out.println(message);
    }
}
~~~

Phương thức **String.strip()** có từ Java 11. Từ thư mục **project**, biên dịch bằng JDK 17 nhưng đặt release là 11:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 11 -d out src/com/example/App.java
java -cp out com.example.App
~~~

Kết quả khi chạy bằng runtime tương thích:

~~~text
Java 11
~~~

Lệnh **java** trong ví dụ cuối cùng sử dụng runtime đang có trên **PATH**. Nếu cần xác nhận tương thích thực tế với Java 11, hãy chạy chương trình bằng executable của Java 11, không chỉ bằng Java 17.

Ví dụ trên chứng minh rằng JDK mới có thể biên dịch mã theo API và bytecode của release cũ mà không cần cài đúng JDK cũ để biên dịch.

## 5. So sánh source, target và release

| Tùy chọn | Điều khiển | Giới hạn API Java Platform? | Khi nào dùng |
|---|---|---|---|
| **--source N** | Cú pháp/ngôn ngữ Java | Không tự giới hạn API | Khi cần kiểm soát source level riêng |
| **--target N** | Định dạng class file | Không tự giới hạn API | Khi cần kiểm soát bytecode target riêng |
| **--source N --target N** | Cú pháp và bytecode | Không tự giới hạn API | Tương thích cú pháp và class file trong môi trường API đã được kiểm soát |
| **--release N** | Cú pháp, bytecode và API nền tảng | Có | Lựa chọn ưu tiên khi build cho một Java release cụ thể |

Ví dụ:

~~~powershell
# Source và target riêng
javac --source 11 --target 11 -d out src/com/example/App.java

# Cách khuyến nghị cho ứng dụng cần chạy trên Java 11
javac --release 11 -d out src/com/example/App.java
~~~

Khi mục tiêu là hỗ trợ một runtime cụ thể, **--release** thường an toàn và rõ ràng hơn.

## 6. Bảng ánh xạ Java release và class file version

Mỗi phiên bản Java tương ứng với một major version của class file. Bảng dưới đây liệt kê một số phiên bản thường gặp:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |

Quy tắc hữu ích từ Java 9 trở đi: major version thường bằng số release cộng 44. Ví dụ Java 17 có major version 61.

Bảng này giúp đọc lỗi kiểu **UnsupportedClassVersionError** và xác định bytecode được biên dịch cho phiên bản nào. Tuy nhiên, major version đúng chưa đủ để chứng minh ứng dụng tương thích: chương trình vẫn có thể phụ thuộc vào API mới, thư viện bên ngoài hoặc hành vi runtime khác.

## 7. Kiểm tra kết quả biên dịch

### 7.1. Kiểm tra bằng javap

**javap** là công cụ đi kèm JDK để đọc thông tin class file. Dùng **-verbose** để xem chi tiết:

~~~powershell
javap -verbose -classpath out com.example.App
~~~

Trong phần đầu ra, tìm dòng **major version**. Nếu biên dịch bằng **--release 11**, class file của ví dụ sẽ có major version 55.

Có thể lọc nhanh trên PowerShell:

~~~powershell
javap -verbose -classpath out com.example.App | Select-String "major version"
~~~

Trên Bash hoặc Zsh, có thể dùng **grep**:

~~~bash
javap -verbose -classpath out com.example.App | grep "major version"
~~~

### 7.2. Kiểm tra phiên bản compiler và runtime

Dùng:

~~~powershell
javac -version
java -version
~~~

Hai lệnh có thể trỏ tới hai bản Java khác nhau nếu PATH hoặc cấu hình môi trường không nhất quán. Kiểm tra cả hai giúp phát hiện trường hợp biên dịch bằng JDK này nhưng chạy bằng runtime khác.

### 7.3. Kiểm tra API và thư viện phụ thuộc

**--release** giới hạn API của Java Platform mà trình biên dịch cho phép sử dụng. Nó không tự kiểm tra mọi thư viện bên ngoài mà ứng dụng phụ thuộc.

Ví dụ, một thư viện bên thứ ba có thể chỉ hỗ trợ Java 17 dù ứng dụng của bạn được biên dịch với **--release 11**. Cần chọn phiên bản thư viện hỗ trợ runtime mục tiêu và kiểm thử toàn bộ ứng dụng trên runtime đó.

## 8. Các giới hạn và lưu ý

### 8.1. Release phải được JDK hiện tại hỗ trợ

Một compiler không thể tạo bytecode cho release mới hơn phiên bản của chính nó. Ví dụ, JDK 17 không thể dùng **--release 21**. Hãy dùng JDK 21 hoặc bản mới hơn để biên dịch cho Java 21.

Với release rất cũ, compiler mới có thể đã ngừng hỗ trợ. Tham khảo **javac --help** của đúng JDK đang sử dụng.

### 8.2. Preview feature

Tính năng preview gắn với phiên bản Java cụ thể. **--enable-preview** chỉ dùng cho release hiện tại của compiler/runtime, và khi biên dịch cần kết hợp với source level tương ứng.

Ví dụ trên JDK 17:

~~~powershell
javac --enable-preview --release 17 -d out src/com/example/PreviewApp.java
java --enable-preview -cp out com.example.PreviewApp
~~~

Không thể dùng preview feature của Java 17 rồi kỳ vọng chạy trên Java 11 chỉ bằng cách đặt **--target 11**.

### 8.3. Annotation processor và thư viện bên ngoài

Annotation processor chạy trong quá trình biên dịch và có thể có yêu cầu JDK riêng. Các dependency dùng lúc biên dịch cũng cần phiên bản phù hợp với compiler và release mục tiêu.

Hãy kiểm tra:

- Phiên bản JDK mà annotation processor hỗ trợ.
- Phiên bản bytecode của thư viện bên ngoài.
- API Java mà thư viện sử dụng.
- Các native library hoặc thành phần phụ thuộc môi trường nếu có.

### 8.4. Build tương thích không thay thế kiểm thử runtime

Ngay cả khi dùng **--release**, ứng dụng vẫn cần được kiểm thử trên runtime mục tiêu. Tương thích còn phụ thuộc thư viện, cấu hình, hệ điều hành, encoding, timezone, TLS, native code và hành vi của ứng dụng.

## 9. Cấu hình source/target trong Maven và Gradle

Với dự án dùng build tool, nên cấu hình release trong build file để mọi máy build sử dụng cùng một mục tiêu.

### 9.1. Maven

Với Maven Compiler Plugin, có thể khai báo thuộc tính release:

~~~xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
~~~

Hoặc cấu hình trực tiếp trong plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>11</release>
    </configuration>
</plugin>
~~~

Dùng một cấu hình release nhất quán và tránh đặt đồng thời các giá trị source/target mâu thuẫn ở nhiều nơi trong POM.

### 9.2. Gradle

Với Gradle Java plugin hiện đại, có thể dùng toolchain và release target:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
~~~

Ví dụ trên dùng JDK 17 để biên dịch và đặt mục tiêu Java 11. Toolchain chọn JDK compiler, còn **options.release** đặt release tương thích cho tác vụ biên dịch. Cú pháp chi tiết có thể thay đổi theo phiên bản Gradle và DSL Groovy/Kotlin mà dự án sử dụng.

## 10. Lỗi thường gặp khi cấu hình source và target

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **invalid source release** | JDK hiện tại không hỗ trợ source level được yêu cầu | Kiểm tra **javac -version** và các release được hỗ trợ |
| **invalid target release** | Target level vượt khả năng compiler hoặc không được hỗ trợ | Dùng JDK phù hợp với target mong muốn |
| **Source option ... is no longer supported** | Dùng source level quá cũ đã bị compiler loại bỏ | Nâng source level hoặc dùng JDK cũ phù hợp nếu dự án bắt buộc |
| **UnsupportedClassVersionError** | Runtime quá cũ so với class file | Biên dịch với release thấp hơn hoặc nâng runtime |
| **NoSuchMethodError** khi chạy trên runtime cũ | Bytecode gọi API không có ở runtime đó | Biên dịch lại bằng **--release** đúng phiên bản và kiểm tra dependency |
| **package ... does not exist** khi dùng **--release** | API/package không thuộc Java Platform release mục tiêu hoặc thiếu dependency | Kiểm tra release mục tiêu và classpath/module path |
| **option --release cannot be used together with --source** | Kết hợp các tùy chọn loại trừ nhau | Chỉ dùng **--release** hoặc cặp **--source**/**--target** |
| Cảnh báo system modules path khi dùng source/target cũ | Compiler đang dùng API của JDK hiện tại mà chưa có platform API path tương ứng | Ưu tiên **--release** để giới hạn API nền tảng |

## 11. Quy trình chọn cấu hình

Khi bắt đầu một dự án hoặc nâng JDK build, thực hiện theo thứ tự:

1. Xác định phiên bản Java thấp nhất mà ứng dụng phải hỗ trợ.
2. Chọn JDK compiler đủ mới để hỗ trợ release đó.
3. Dùng **javac --release N** với N là runtime mục tiêu.
4. Kiểm tra thư viện bên ngoài, annotation processor và plugin có hỗ trợ N hay không.
5. Dùng **javap -verbose** để kiểm tra major version của class file.
6. Chạy kiểm thử trên đúng runtime N.
7. Đưa cấu hình release vào Maven/Gradle hoặc script build dùng chung để tránh sai khác giữa máy phát triển và CI.

## 12. Checklist trước khi phát hành

- [ ] Đã xác định runtime Java thấp nhất cần hỗ trợ.
- [ ] Đã chọn JDK compiler có hỗ trợ release mục tiêu.
- [ ] Đã dùng **--release** khi cần tương thích cả cú pháp, bytecode và Java Platform API.
- [ ] Không trộn **--release** với **--source** hoặc **--target** trong cùng lệnh.
- [ ] Đã kiểm tra major version bằng **javap -verbose**.
- [ ] Các thư viện bên ngoài và annotation processor tương thích runtime mục tiêu.
- [ ] Preview feature chỉ được dùng với đúng phiên bản Java hỗ trợ chúng.
- [ ] Đã chạy kiểm thử trên runtime thực tế thấp nhất cần hỗ trợ.
- [ ] Build file và CI dùng cùng cấu hình release.

**--source** điều khiển cú pháp Java, **--target** điều khiển định dạng bytecode, còn **--release** kết hợp cả hai với giới hạn Java Platform API. Khi biên dịch bằng JDK mới để hỗ trợ runtime cũ, hãy ưu tiên **--release** và xác minh bằng cách chạy thử trên đúng phiên bản Java mục tiêu.
