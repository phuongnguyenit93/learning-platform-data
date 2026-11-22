# Chọn source khi tạo tài liệu bằng Javadoc

Khi chạy công cụ `javadoc`, bạn cần xác định **những mã nguồn Java nào sẽ được đưa vào tài liệu API**. Đây là bước chọn source (source selection). Javadoc có thể nhận danh sách tệp `.java` cụ thể, tên package, một cây package cần quét đệ quy hoặc danh sách module.

Chọn source đúng giúp tài liệu chỉ bao gồm API cần công bố, tránh bỏ sót package, tránh đưa mã nội bộ vào tài liệu công khai và giúp lệnh build có thể lặp lại.

## 1. Các cách chọn source

Javadoc hỗ trợ ba cách chọn đầu vào phổ biến:

1. **Chọn tệp nguồn cụ thể:** truyền trực tiếp đường dẫn các tệp `.java`.
2. **Chọn package:** truyền tên package và dùng `-sourcepath` để Javadoc tìm mã nguồn.
3. **Chọn cây package:** dùng `-subpackages` để quét một package gốc cùng các package con.

Với dự án dùng Java Platform Module System (JPMS), có thể chọn module bằng `--module-source-path` và `--module`.

Cú pháp tổng quát:

```text
javadoc [options] [packagenames] [sourcefiles] [@argfiles]
```

- `options`: tùy chọn như thư mục đầu ra, source path, encoding và mức hiển thị.
- `packagenames`: tên một hoặc nhiều package cần tạo tài liệu.
- `sourcefiles`: đường dẫn các tệp nguồn cần tạo tài liệu.
- `@argfiles`: tệp chứa danh sách đối số để tránh lệnh quá dài.

Các cách chọn source xác định phạm vi lớp và package được xử lý. Chúng độc lập với mức hiển thị thành viên như public, protected hoặc private.

## 2. Chọn từng tệp .java cụ thể

Khi chỉ muốn tạo tài liệu cho một số lớp nhất định, truyền trực tiếp đường dẫn tệp nguồn.

Ví dụ cấu trúc:

```text
project/
  src/
    com/
      example/
        math/
          package-info.java
          Calculator.java
          internal/
            BigMath.java
```

Tạo tài liệu cho package comment và lớp `Calculator`:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src src/com/example/math/package-info.java src/com/example/math/Calculator.java
```

Ý nghĩa:

- `-d docs`: ghi HTML vào thư mục `docs`.
- `-encoding UTF-8`: đọc mã nguồn bằng UTF-8.
- `-sourcepath src`: cho phép Javadoc tìm các tệp nguồn liên quan trong thư mục `src`.
- Hai đường dẫn cuối là các source file được chọn rõ ràng.

Cách này phù hợp khi:

- Chỉ muốn công bố một phần API.
- Muốn tạo tài liệu cho một vài class độc lập.
- Đang thử nghiệm một lớp hoặc một nhóm lớp nhỏ.
- Có mã nguồn nội bộ không muốn đưa vào tài liệu công khai.

Nếu muốn tài liệu package, hãy đưa `package-info.java` vào danh sách khi cần mô tả package. Không nên giả định rằng chỉ truyền một class bất kỳ sẽ tự động chọn mọi package con hoặc mọi tệp nguồn cùng thư mục.

## 3. Chọn package bằng tên package

Thay vì liệt kê từng tệp, có thể truyền tên package. Javadoc tìm mã nguồn package dựa trên source path.

Ví dụ:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src com.example.math
```

Trong đó:

- `-sourcepath src` chỉ định thư mục gốc chứa cây mã nguồn.
- `com.example.math` là tên package Java, dùng dấu chấm phân cách các thành phần.
- Javadoc tìm các source file thuộc package được chỉ định và tạo tài liệu theo mức hiển thị mặc định.

Với cấu trúc:

```text
src/
  com/
    example/
      math/
        package-info.java
        Calculator.java
        internal/
          BigMath.java
```

Package `com.example.math` tương ứng với thư mục:

```text
src/com/example/math/
```

Tên package truyền cho Javadoc không phải đường dẫn thư mục. Hãy dùng `com.example.math`, không dùng `src/com/example/math`.

Chọn package trực tiếp phù hợp khi dự án có nhiều package và bạn chỉ muốn tạo tài liệu cho một số package cụ thể.

## 4. Chọn package và các package con bằng -subpackages

Nếu muốn tạo tài liệu cho toàn bộ một nhánh package, dùng `-subpackages`.

Ví dụ:

```bash
javadoc -d docs -encoding UTF-8 -sourcepath src -subpackages com.example
```

Lệnh trên yêu cầu Javadoc tìm package `com.example` và các package con trong source path, ví dụ:

```text
com.example
com.example.math
com.example.math.internal
com.example.app
com.example.persistence
```

Điểm cần nhớ:

- `-subpackages` nhận tên package gốc, không nhận đường dẫn thư mục.
- Javadoc quét các package con trong source path.
- Chỉ các package tìm thấy trong source path mới được xử lý.
- Chọn package gốc rộng có thể làm tài liệu bao gồm nhiều API hơn dự kiến.

Dùng `-subpackages` khi muốn tạo tài liệu cho một thư viện có nhiều package liên quan và muốn tránh liệt kê từng package bằng tay.

## 5. Loại trừ package bằng -exclude

Khi quét đệ quy bằng `-subpackages`, đôi khi cần bỏ qua package nội bộ hoặc package thử nghiệm. Dùng `-exclude` để loại trừ package và các package con của nó khỏi tập được chọn.

Ví dụ:

```bash
javadoc -d docs -sourcepath src -subpackages com.example -exclude com.example.internal
```

Giả sử source tree có:

```text
com.example
com.example.api
com.example.model
com.example.internal
com.example.internal.codegen
com.example.test
```

Lệnh trên loại `com.example.internal` và nhánh con `com.example.internal.codegen` khỏi tập package được chọn. Các package khác trong nhánh `com.example` vẫn có thể được xử lý.

Có thể dùng `-exclude` để giữ tài liệu công khai tập trung vào API mà người dùng thư viện cần biết.

Lưu ý:

- `-exclude` được dùng cùng lựa chọn `-subpackages`.
- Tên package phải đúng chính tả và phân biệt chữ hoa/chữ thường.
- Loại trừ package khỏi tài liệu không xóa mã nguồn hoặc ngăn ứng dụng biên dịch package đó.
- Nếu một package nội bộ được chọn riêng bằng danh sách source file hoặc package khác, hãy kiểm tra lại phạm vi đầu vào tổng thể.

## 6. Source path khác classpath như thế nào?

Hai tùy chọn này có mục đích khác nhau:

| Tùy chọn | Dùng để tìm | Mục đích |
| --- | --- | --- |
| `-sourcepath` | Tệp nguồn `.java` | Tìm mã nguồn của package/type được chọn hoặc cần phân giải |
| `-classpath` / `--class-path` | Class file và JAR | Tìm các kiểu đã biên dịch mà source đang tham chiếu |

Ví dụ dự án có:

```text
project/
  src/
    com/example/api/Client.java
  lib/
    helper.jar
```

Tạo tài liệu cho source trong `src`, đồng thời dùng JAR để phân giải kiểu phụ thuộc:

```bash
javadoc -d docs -sourcepath src --class-path lib/helper.jar com.example.api
```

`lib/helper.jar` giúp Javadoc tìm kiểu đã biên dịch được tham chiếu trong mã nguồn. Nó không có nghĩa là Javadoc tự động tạo tài liệu cho mọi lớp trong JAR đó.

Nếu muốn tài liệu cho mã nguồn của thư viện, cần cung cấp source file hoặc package tương ứng qua source selection. Nếu chỉ có JAR mà không có source, có thể dùng JAR để phân giải kiểu nhưng không thể tạo tài liệu đầy đủ từ doc comment nguồn của thư viện đó theo cách thông thường.

Khi không chỉ định `-sourcepath`, Javadoc có thể dùng classpath làm nơi tìm nguồn theo quy tắc mặc định. Trong dự án thực tế, nên chỉ rõ source path để lệnh tạo tài liệu dễ hiểu và ổn định.

## 7. Chọn nhiều package hoặc nhiều source file

Có thể chọn nhiều package bằng cách liệt kê tên package:

```bash
javadoc -d docs -sourcepath src com.example.api com.example.model
```

Hoặc truyền nhiều source file:

```bash
javadoc -d docs -sourcepath src src/com/example/api/Client.java src/com/example/model/User.java
```

Dùng cách này khi chỉ muốn tạo tài liệu cho các phần API được chọn rõ ràng. Hãy kiểm tra package comment và các type liên quan nếu chúng cũng cần xuất hiện trong tài liệu.

Với dự án lớn, liệt kê tất cả source file trên một lệnh có thể làm lệnh khó đọc. Có thể dùng argument file để quản lý danh sách.

## 8. Dùng argument file (@file)

Javadoc hỗ trợ đọc tùy chọn và đối số từ một tệp bằng cú pháp `@tên-tệp`. Cách này hữu ích khi danh sách source file hoặc package dài.

Ví dụ tệp **`javadoc.args`**:

```text
-d
docs
-encoding
UTF-8
-sourcepath
src
com.example.api
com.example.model
```

Chạy:

```bash
javadoc @javadoc.args
```

Có thể lưu danh sách source file thay cho package name:

```text
-d
docs
-sourcepath
src
src/com/example/api/package-info.java
src/com/example/api/Client.java
src/com/example/model/User.java
```

Ưu điểm:

- Lệnh terminal ngắn hơn.
- Danh sách đầu vào được lưu trong repository và review cùng thay đổi.
- Dễ tái sử dụng trong CI.
- Tránh lỗi khi lệnh chứa quá nhiều đối số.

Khi dùng argument file, hãy kiểm tra đường dẫn tương đối theo thư mục làm việc lúc chạy lệnh và dùng dấu nháy phù hợp nếu đường dẫn chứa khoảng trắng. Không nên để danh sách package và source file vô tình trỏ đến nhiều phiên bản của cùng một source tree.

## 9. Chọn source cho dự án modular

Với JPMS, source của mỗi module thường nằm trong một thư mục riêng dưới module source path.

Ví dụ:

```text
project/
  src/
    com.example.math/
      module-info.java
      com/example/math/
        package-info.java
        Calculator.java
    com.example.app/
      module-info.java
      com/example/app/
        Main.java
```

Dùng `--module-source-path` để chỉ định gốc của cây source module và `--module` để chọn module cần tạo tài liệu.

Ví dụ tạo tài liệu cho module số học:

```bash
javadoc --module-source-path src -d docs --module com.example.math
```

Tạo tài liệu cho cả hai module:

```bash
javadoc --module-source-path src -d docs --module com.example.math,com.example.app
```

Ý nghĩa:

- `--module-source-path src`: chỉ nơi chứa các thư mục source module.
- `--module com.example.math`: chọn module có tên tương ứng.
- `-d docs`: lưu tài liệu HTML.

Nếu module cần các module đã biên dịch hoặc dependency khác để phân giải kiểu, có thể chỉ định module path phù hợp bằng `--module-path`.

Phân biệt:

- `--module-source-path`: nơi tìm mã nguồn module.
- `--module-path`: nơi tìm các module đã biên dịch để phân giải dependency.

Không dùng tên package thay cho tên module trong tùy chọn `--module`. Tên module lấy từ khai báo `module` trong `module-info.java`.

## 10. Ví dụ hoàn chỉnh: chọn source trong một thư viện

Ví dụ sau tạo tài liệu cho API công khai trong package `com.example.math`, đồng thời loại trừ package nội bộ.

Cấu trúc dự án:

```text
project/
  src/
    com/example/math/
      package-info.java
      Calculator.java
      internal/
        BigMath.java
    com/example/app/
      Main.java
  docs/
```

Tệp **`src/com/example/math/package-info.java`**:

```java
/**
 * Cung cấp các phép toán số học cho ứng dụng.
 */
package com.example.math;
```

Tệp **`src/com/example/math/Calculator.java`**:

```java
package com.example.math;

/**
 * Cung cấp các phép toán số nguyên cơ bản.
 */
public final class Calculator {
    private Calculator() {
    }

    /**
     * Cộng hai số nguyên.
     *
     * @param left toán hạng thứ nhất
     * @param right toán hạng thứ hai
     * @return tổng của hai số
     */
    public static int add(int left, int right) {
        return left + right;
    }
}
```

Tệp **`src/com/example/math/internal/BigMath.java`**:

```java
package com.example.math.internal;

/**
 * Các tiện ích triển khai nội bộ.
 */
public final class BigMath {
    private BigMath() {
    }

    /**
     * Trả về bình phương của một số.
     *
     * @param value giá trị đầu vào
     * @return bình phương
     */
    public static long square(long value) {
        return value * value;
    }
}
```

Tệp **`src/com/example/app/Main.java`**:

```java
package com.example.app;

import com.example.math.Calculator;

public class Main {
    public static void main(String[] args) {
        System.out.println("sum=" + Calculator.add(7, 5));
    }
}
```

### Bước 1: Chọn riêng package API

Chạy từ thư mục gốc `project`:

```bash
javadoc -d docs-api -encoding UTF-8 -sourcepath src com.example.math
```

Javadoc tạo tài liệu cho package `com.example.math`. Package `com.example.math.internal` không được tự động chọn chỉ vì nó là package con; lệnh này chọn package được nêu trực tiếp.

### Bước 2: Chọn cả nhánh package nhưng loại trừ internal

Chạy:

```bash
javadoc -d docs-public -encoding UTF-8 -sourcepath src -subpackages com.example -exclude com.example.math.internal
```

Lệnh này quét nhánh `com.example`, nhưng bỏ package `com.example.math.internal` và nhánh con của nó khỏi tập được chọn.

### Bước 3: Chọn đúng một source file

Nếu chỉ cần tài liệu cho `Calculator` và package summary:

```bash
javadoc -d docs-single -encoding UTF-8 -sourcepath src src/com/example/math/package-info.java src/com/example/math/Calculator.java
```

### Bước 4: Biên dịch và chạy ứng dụng riêng

Javadoc tạo HTML, không tạo bytecode. Để kiểm tra chương trình:

```bash
javac -d out -sourcepath src src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Kết quả chính xác:

```text
sum=12
```

Ví dụ cho thấy source selection quyết định phần mã nguồn được đưa vào tài liệu, còn `javac` vẫn chịu trách nhiệm biên dịch chương trình.

## 11. Mức hiển thị thành viên không phải source selection

Một nhầm lẫn thường gặp là coi `-private` hoặc `-public` như cách chọn source. Thực tế, các tùy chọn này quyết định mức thành viên được đưa vào trang tài liệu sau khi source/package đã được chọn.

| Tùy chọn | Thành viên được hiển thị |
| --- | --- |
| `-public` | Chỉ public |
| `-protected` | Public và protected; mức mặc định |
| `-package` | Public, protected và package-private |
| `-private` | Tất cả, kể cả private |

Ví dụ:

```bash
javadoc -d docs-internal -private -sourcepath src com.example.math
```

Lệnh vẫn chọn package `com.example.math`, nhưng tài liệu bao gồm cả thành viên private.

Ngược lại:

```bash
javadoc -d docs-public -public -sourcepath src com.example.math
```

Lệnh chọn cùng package nhưng chỉ hiển thị thành viên public.

Khi tạo tài liệu API công khai, thường nên dùng mức mặc định hoặc `-public`. Chỉ dùng `-private` cho tài liệu nội bộ khi có lý do phù hợp.

## 12. Chọn source trong Maven và Gradle

Trong dự án dùng build tool, source selection thường dựa trên source set hoặc cấu hình plugin.

### Maven

Maven Javadoc Plugin thường lấy mã nguồn từ source roots của Maven project. Có thể tạo tài liệu bằng:

```bash
mvn javadoc:javadoc
```

Nếu chỉ muốn tài liệu cho một tập package hoặc cấu hình source đặc biệt, truyền các tùy chọn Javadoc qua cấu hình plugin, ví dụ `sourcepath`, `subpackages` hoặc các tham số phù hợp với phiên bản plugin. Cần kiểm tra cấu hình plugin vì tên tham số có thể khác với tùy chọn CLI trực tiếp.

### Gradle

Với Gradle Java plugin, tác vụ `javadoc` sử dụng source của main source set theo mặc định. Có thể xem hoặc tùy chỉnh source của tác vụ:

```groovy
tasks.named('javadoc', Javadoc) {
    source = sourceSets.main.allJava
    options.encoding = 'UTF-8'
}
```

Chạy:

```bash
./gradlew javadoc
```

Trên Windows:

```powershell
.\gradlew.bat javadoc
```

Trong build đa module, mỗi module thường có tác vụ Javadoc riêng. Hãy xác định rõ source set nào được đưa vào tài liệu để tránh vô tình đưa test source hoặc generated source không mong muốn.

## 13. Các lỗi thường gặp khi chọn source

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Javadoc báo không tìm thấy package | Tên package sai hoặc source path không trỏ đến gốc source | Kiểm tra package declaration và `-sourcepath` |
| Không thấy package con | Chỉ truyền tên package cha mà không dùng `-subpackages` | Dùng `-subpackages` khi muốn quét đệ quy |
| Tài liệu chứa package nội bộ | Chọn package gốc quá rộng | Dùng `-exclude` hoặc chọn package cụ thể |
| Thiếu package summary | Không đưa `package-info.java` vào danh sách source file hoặc package không được chọn đúng | Chọn package hoặc thêm `package-info.java` |
| Javadoc không phân giải được kiểu phụ thuộc | Thiếu classpath hoặc module path | Bổ sung `--class-path` hoặc `--module-path` |
| Tài liệu có quá nhiều thành viên | Dùng `-private` ngoài ý muốn | Dùng `-public` hoặc mức mặc định |
| Không có tài liệu cho JAR dependency | Chỉ thêm JAR vào classpath | Cung cấp source/package tương ứng nếu muốn tạo tài liệu cho thư viện |
| Module không được tìm thấy | Nhầm module source path với module path hoặc tên module sai | Kiểm tra `--module-source-path`, `--module-path` và `--module` |
| Lệnh quá dài hoặc dễ thiếu file | Liệt kê nhiều source file trực tiếp | Dùng argument file `@javadoc.args` |

## 14. Quy trình chọn source đề xuất

Trước khi chạy Javadoc, hãy xác định:

1. **Mục tiêu tài liệu:** API công khai, tài liệu nội bộ hay một nhóm lớp thử nghiệm?
2. **Kiểu dự án:** source tree thông thường hay modular project?
3. **Phạm vi package:** một package, nhiều package hay toàn bộ nhánh package?
4. **Source đầu vào:** truyền file cụ thể, package name, `-subpackages` hay `--module`?
5. **Package cần loại trừ:** có package internal, generated hoặc test cần bỏ qua không?
6. **Dependency để phân giải:** cần `--class-path` hay `--module-path`?
7. **Mức hiển thị:** public/protected hay cần cả package-private/private?
8. **Tính lặp lại:** có nên lưu danh sách đầu vào trong argument file hoặc build script?

Sau khi chọn source, chạy Javadoc, kiểm tra các trang package/class được tạo và xác nhận không thiếu hoặc thừa package so với phạm vi mong muốn.

## 15. Ghi nhớ

- Javadoc có thể nhận source file cụ thể, tên package hoặc danh sách argument file.
- Dùng `-sourcepath` để chỉ gốc cây mã nguồn khi chọn package.
- Dùng `-subpackages` để chọn một package và các package con.
- Dùng `-exclude` để loại trừ package và nhánh con khi quét bằng `-subpackages`.
- Dùng `--module-source-path` và `--module` để chọn module trong dự án JPMS.
- Dùng `--class-path` hoặc `--module-path` để phân giải dependency; chúng không tự chọn source cần tạo tài liệu.
- `-public`, `-protected`, `-package` và `-private` điều khiển mức hiển thị thành viên, không phải phạm vi source.
- Dùng `@argfile` để quản lý danh sách đầu vào dài và có thể tái sử dụng.

Chọn source rõ ràng giúp tài liệu Javadoc phản ánh đúng API cần công bố, dễ kiểm tra trong code review và có thể tái tạo nhất quán trong quy trình build.
