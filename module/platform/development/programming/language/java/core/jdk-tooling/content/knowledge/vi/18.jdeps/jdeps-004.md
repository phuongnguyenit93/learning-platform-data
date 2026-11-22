# Phân tích dependency package bằng jdeps

**jdeps** là công cụ phân tích dependency của Java, được cung cấp cùng JDK. Công cụ đọc class file, thư mục class hoặc JAR để xác định các lớp và package mà artifact đang phụ thuộc. Kết quả giúp developer hiểu package nào sử dụng package nào, thư viện nào cần module nào và dependency nào có thể gây khó khăn khi nâng cấp hoặc chuyển ứng dụng sang Java Platform Module System (JPMS).

Một lệnh thường dùng để xem dependency ở cấp package:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Lệnh này phân tích các class trong build/classes và hiển thị quan hệ package nguồn → package đích. Tùy chọn -filter:none yêu cầu hiển thị cả dependency nội bộ cùng archive hoặc package; nếu bỏ tùy chọn này, một số quan hệ nội bộ được lọc theo mặc định.

jdeps thực hiện phân tích tĩnh trên bytecode và metadata có sẵn. Nó không chạy ứng dụng, không đo tần suất gọi method và không thể phát hiện mọi dependency được nạp động bằng reflection, tên class dạng chuỗi, cấu hình bên ngoài hoặc mã native.

## 1. Dependency package là gì?

Một package dependency tồn tại khi class thuộc package này tham chiếu tới class thuộc package khác. Tham chiếu có thể xuất hiện trong:

- Superclass hoặc interface được implement.
- Kiểu của field.
- Kiểu tham số hoặc kiểu trả về của method.
- Kiểu exception được khai báo.
- Lệnh tạo object, gọi method hoặc truy cập field.
- Annotation, generic signature và các metadata khác được lưu trong class file.

Ví dụ:

~~~java
package com.example.app;

import com.example.data.Customer;
import com.example.format.NameFormatter;

public class Main {
    public static void main(String[] args) {
        Customer customer = Customer.sample();
        System.out.println(NameFormatter.format(customer.name()));
    }
}
~~~

Class Main trong package com.example.app sử dụng kiểu Customer thuộc com.example.data và NameFormatter thuộc com.example.format. Vì vậy, package com.example.app có dependency tới hai package kia.

Có thể hình dung đồ thị:

~~~text
com.example.app
    |--------------------|
    v                    v
com.example.data    com.example.format
~~~

Mũi tên biểu thị package nguồn phụ thuộc vào package đích. Nó không có nghĩa package đích phụ thuộc ngược lại.

Package dependency giúp trả lời các câu hỏi kiến trúc:

- Package nào đang phụ thuộc vào package nào?
- Một package nội bộ có bị sử dụng từ nhiều nơi không?
- Có dependency vòng giữa các package không?
- Thay đổi một package có thể ảnh hưởng tới những package nào?
- Thư viện cần những module hoặc JDK package nào?
- Có đang sử dụng API nội bộ của JDK không?

## 2. jdeps phân tích điều gì?

jdeps đọc class file đã biên dịch. Nó tìm các tham chiếu mà bytecode và metadata thể hiện, sau đó nhóm hoặc lọc dependency theo cấp package, class, archive hay module.

Có ba cấp độ thường dùng:

| Cấp độ | Tùy chọn | Nội dung |
|---|---|---|
| Package | -verbose:package | Quan hệ package nguồn và package đích |
| Class | -verbose:class | Quan hệ class nguồn và class đích |
| Summary | -summary | Tóm tắt dependency ở cấp archive/module |

### Phân tích package

~~~bash
jdeps -verbose:package build/classes
~~~

Đây là lựa chọn phù hợp khi muốn xem cấu trúc dependency giữa các package. Theo mặc định, dependency nội bộ trong cùng package thường được lọc để output tập trung vào quan hệ giữa các package.

### Phân tích class

~~~bash
jdeps -verbose:class build/classes
~~~

Kết quả chi tiết hơn, cho biết class nào tham chiếu class nào. Cấp class hữu ích khi cần truy vết một dependency cụ thể hoặc tìm class tạo ra sự phụ thuộc ngoài dự kiến.

Tùy chọn -v hoặc --verbose tương đương phân tích class-level với bộ lọc bị tắt. Nó có thể tạo output lớn hơn đáng kể.

### Summary

~~~bash
jdeps -summary build/classes
~~~

Summary gom dependency ở cấp archive/module, giúp có cái nhìn tổng quan trước khi đi sâu vào package hoặc class.

Không nên dùng summary để kết luận một package cụ thể đang gọi package nào; nó đã tổng hợp thông tin ở cấp cao hơn.

## 3. Đầu vào mà jdeps có thể phân tích

jdeps nhận một hoặc nhiều đường dẫn:

- Một file .class.
- Một thư mục chứa các class file.
- Một file JAR.
- Một modular JAR hoặc module có thể được tìm trên module path.

Ví dụ phân tích một JAR:

~~~bash
jdeps -verbose:package lib/customer-service.jar
~~~

Phân tích toàn bộ thư mục output:

~~~bash
jdeps -verbose:package build/classes
~~~

Phân tích nhiều JAR:

~~~bash
jdeps -summary lib/customer-api.jar lib/customer-impl.jar
~~~

Với một thư mục class, jdeps đọc các class bên trong và xác định dependency giữa chúng với các package bên ngoài. Với JAR, nó phân tích nội dung archive và hiển thị tên archive làm nguồn dependency.

Nếu một dependency không nằm trong đầu vào hoặc đường dẫn tìm kiếm, jdeps có thể báo không tìm thấy class hoặc dependency. Cần cung cấp classpath/module path thích hợp để kết quả đầy đủ hơn.

## 4. Cách đọc output package-level

Một dòng output thường có cấu trúc:

~~~text
source.package -> target.package target-location
~~~

Ví dụ:

~~~text
classes -> java.base
   com.example.app    -> com.example.data    classes
   com.example.app    -> com.example.format  classes
   com.example.app    -> java.lang           java.base
   com.example.data   -> java.time           java.base
   com.example.format -> java.util           java.base
~~~

Ý nghĩa:

- classes là archive hoặc thư mục đầu vào được phân tích.
- com.example.app là package nguồn.
- com.example.data là package đích.
- classes ở cột cuối cho biết package đích nằm trong cùng thư mục/archive đầu vào.
- java.base cho biết package đích thuộc module java.base.

Một package có thể phụ thuộc nhiều package khác. Một package đích cũng có thể được nhiều package nguồn sử dụng.

### Dependency nội bộ và bên ngoài

Dependency nội bộ là quan hệ giữa các package nằm trong cùng archive hoặc thư mục đầu vào. Dependency bên ngoài trỏ tới package ở archive, JAR hoặc module khác.

Bộ lọc mặc định của jdeps có thể ẩn dependency nội bộ cùng package hoặc cùng archive. Dùng -filter:none khi cần nhìn đầy đủ hơn.

### Dependency là một chiều

Nếu output có:

~~~text
com.example.app -> com.example.data
~~~

điều đó thể hiện app tham chiếu data. Không thể suy ra data tham chiếu app. Muốn biết dependency ngược, phải xem một dòng riêng hoặc chạy phân tích inverse.

## 5. Ví dụ thực hành Java 17+: ba package

Ví dụ gồm ba package:

- com.example.app chứa điểm khởi chạy.
- com.example.data chứa record Customer.
- com.example.format chứa logic định dạng tên.

Cấu trúc source:

~~~text
jdeps-demo/
└── src/
    └── com/
        └── example/
            ├── app/
            │   └── Main.java
            ├── data/
            │   └── Customer.java
            └── format/
                └── NameFormatter.java
~~~

### Customer.java

~~~java
package com.example.data;

import java.time.LocalDate;

public record Customer(String name, LocalDate since) {
}
~~~

Customer phụ thuộc vào LocalDate trong java.time.

### NameFormatter.java

~~~java
package com.example.format;

import java.util.Locale;

public final class NameFormatter {
    private NameFormatter() {
    }

    public static String format(String name) {
        return name.toUpperCase(Locale.ROOT);
    }
}
~~~

NameFormatter phụ thuộc vào Locale trong java.util.

### Main.java

~~~java
package com.example.app;

import com.example.data.Customer;
import com.example.format.NameFormatter;
import java.time.LocalDate;

public final class Main {
    public static void main(String[] args) {
        Customer customer =
                new Customer("Ada", LocalDate.of(2020, 1, 1));

        System.out.println(
                NameFormatter.format(customer.name())
                        + " since " + customer.since());
    }
}
~~~

Main phụ thuộc vào Customer, NameFormatter và LocalDate.

### Biên dịch

Từ thư mục gốc jdeps-demo:

~~~bash
mkdir -p build/classes

javac --release 17 -d build/classes \
    src/com/example/data/Customer.java \
    src/com/example/format/NameFormatter.java \
    src/com/example/app/Main.java
~~~

### Chạy ứng dụng

~~~bash
java -cp build/classes com.example.app.Main
~~~

Output:

~~~text
ADA since 2020-01-01
~~~

### Phân tích dependency package

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Trên JDK 24, output của ví dụ có dạng:

~~~text
classes -> java.base
   com.example.app    -> com.example.data    classes
   com.example.app    -> com.example.format  classes
   com.example.app    -> java.io             java.base
   com.example.app    -> java.lang           java.base
   com.example.app    -> java.lang.invoke    java.base
   com.example.app    -> java.time           java.base
   com.example.data   -> java.lang           java.base
   com.example.data   -> java.lang.invoke    java.base
   com.example.data   -> java.lang.runtime   java.base
   com.example.data   -> java.time           java.base
   com.example.format -> java.lang           java.base
   com.example.format -> java.util           java.base
~~~

Một số chi tiết bytecode hoặc output có thể thay đổi theo compiler/JDK, nhưng hai quan hệ quan trọng của ứng dụng vẫn là:

- com.example.app → com.example.data.
- com.example.app → com.example.format.

Các package java.lang, java.time và java.util thuộc module java.base. Những package như java.lang.invoke có thể xuất hiện do bytecode được compiler tạo ra, ví dụ string concatenation hoặc record support.

### Summary

~~~bash
jdeps -summary build/classes
~~~

Output quan sát trên JDK 24:

~~~text
classes -> java.base
~~~

Summary cho thấy toàn bộ thư mục class phụ thuộc vào java.base. Nó không liệt kê từng package; hãy dùng -verbose:package khi cần chi tiết.

## 6. Classpath và dependency ngoài

Nếu class cần phân tích tham chiếu tới thư viện ngoài, hãy đưa thư viện đó vào classpath của jdeps.

Ví dụ:

~~~bash
jdeps --class-path "lib/customer-api.jar;lib/common.jar" \
    -verbose:package \
    build/classes
~~~

Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy. Trên Linux/macOS, dấu phân cách là dấu hai chấm:

~~~bash
jdeps --class-path "lib/customer-api.jar:lib/common.jar" \
    -verbose:package \
    build/classes
~~~

Nếu không cung cấp dependency cần thiết, output có thể chứa cảnh báo hoặc báo thiếu class. Không nên bỏ qua cảnh báo đó khi mục tiêu là lập bản đồ dependency đầy đủ.

### Chỉ định classpath bằng -cp

Các dạng sau tương đương:

~~~bash
jdeps -cp lib/common.jar build/classes
jdeps -classpath lib/common.jar build/classes
jdeps --class-path lib/common.jar build/classes
~~~

Nên dùng dạng dài --class-path trong script build để người đọc hiểu rõ mục đích.

Classpath cung cấp nơi tìm class của thư viện không modular. Nó không tạo quan hệ module JPMS và không thay thế module path.

## 7. Phân tích theo module path

Với ứng dụng modular, dùng --module-path để chỉ định nơi tìm modular JAR hoặc exploded module.

~~~bash
jdeps --module-path mlib \
    --module com.example.app \
    -verbose:package
~~~

Trong đó:

- --module-path mlib xác định nơi tìm các module.
- --module com.example.app chọn module gốc cần phân tích.
- -verbose:package hiển thị dependency ở cấp package.

Có thể chỉ định module bổ sung vào root set bằng --add-modules:

~~~bash
jdeps --module-path mlib \
    --add-modules com.example.app,com.example.provider \
    -verbose:package
~~~

Nếu muốn phân tích module của JDK, jdeps có thể đọc module từ runtime image hiện tại.

Ví dụ phân tích module java.sql:

~~~bash
jdeps --module java.sql --summary
~~~

Để xem module dependency:

~~~bash
jdeps --list-deps --module java.sql
~~~

Output quan sát trên JDK 24:

~~~text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
~~~

Danh sách cho biết module java.sql phụ thuộc vào các module được liệt kê. Dòng có package nội bộ như java.base/jdk.internal.reflect là tín hiệu cần xem xét kỹ khi đánh giá API hoặc khả năng tương thích.

## 8. Các chế độ phân tích module dependency

jdeps có một số chế độ riêng cho module graph.

### --list-deps

~~~bash
jdeps --list-deps --module java.sql
~~~

Liệt kê module dependency. Nếu class tham chiếu tới package nội bộ của JDK, output cũng có thể thể hiện package nội bộ đó.

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps --module java.sql
~~~

Tùy chọn này loại bỏ các cạnh readability đã được suy ra từ requires transitive. Nó cho thấy graph rút gọn thay vì liệt kê mọi cạnh được hàm ý.

### --print-module-deps

~~~bash
jdeps --print-module-deps --module java.sql
~~~

Output là danh sách module phân tách bằng dấu phẩy:

~~~text
java.base,java.logging,java.transaction.xa,java.xml
~~~

Danh sách này có thể được dùng làm đầu vào cho jlink --add-modules khi tạo custom runtime image, sau khi đã đánh giá module graph và dependency thực tế của ứng dụng.

### --check

~~~bash
jdeps --check java.sql
~~~

Lệnh này phân tích descriptor của module, dependency sau khi phân tích và graph sau transition reduction. Nó cũng có thể chỉ ra qualified export không được sử dụng.

Output thực tế trên JDK 24 bắt đầu như sau:

~~~text
java.sql (jrt:/java.sql)
  [Module descriptor]
    requires mandated java.base;
    requires transitive java.logging;
    requires transitive java.transaction.xa;
    requires transitive java.xml;
~~~

Đây là ví dụ từ module JDK java.sql; module ứng dụng của bạn sẽ có descriptor và dependency riêng.

## 9. Dependency trực tiếp và dependency bắc cầu

Khi một package sử dụng package khác, đó là dependency trực tiếp trong bytecode mà jdeps phát hiện.

Ví dụ:

~~~text
app -> service -> repository -> database
~~~

Nếu app tham chiếu service, service tham chiếu repository và repository tham chiếu database, app có dependency trực tiếp tới service và dependency gián tiếp tới các phần ở phía sau nếu phân tích đệ quy.

Tùy chọn --recursive hoặc -R yêu cầu jdeps đi tiếp qua dependency runtime. Tùy chọn này cũng hàm ý -filter:none, vì vậy output có thể lớn hơn nhiều.

~~~bash
jdeps --recursive -verbose:package build/classes
~~~

Nếu chỉ muốn xem dependency của đầu vào ban đầu, không đi sâu vào dependency bên ngoài:

~~~bash
jdeps --no-recursive -verbose:package build/classes
~~~

Cần phân biệt:

- **Dependency trực tiếp:** class/package đầu vào tham chiếu trực tiếp tới package đích.
- **Dependency bắc cầu:** xuất hiện khi tiếp tục phân tích các dependency của package đích.
- **Module requires transitive:** directive JPMS công khai dependency tới module phụ thuộc; đây là khái niệm module, không đồng nhất với mọi đường đi bắc cầu của package graph.

Không nên gọi mọi dependency bắc cầu là requires transitive. Hai khái niệm thuộc hai mức phân tích khác nhau.

## 10. Lọc dependency để tìm đúng vấn đề

jdeps cung cấp các bộ lọc giúp giảm output.

### Lọc theo package

~~~bash
jdeps --package java.time -verbose:package build/classes
~~~

Hoặc:

~~~bash
jdeps -p java.time -verbose:package build/classes
~~~

Tùy chọn package tìm dependency khớp package được chỉ định. Có thể truyền nhiều package option. Dùng khi muốn tập trung vào một package cụ thể.

### Lọc theo regular expression

~~~bash
jdeps --regex "java\..*" -verbose:package build/classes
~~~

Regex giúp lọc dependency theo pattern, ví dụ các package thuộc java.*. Hãy chú ý cách shell xử lý dấu gạch chéo ngược và dấu nháy trên từng nền tảng.

### Lọc theo module

~~~bash
jdeps --require java.base -verbose:package build/classes
~~~

Tùy chọn --require lọc dependency theo tên module.

Các tùy chọn --package, --regex và --require loại trừ lẫn nhau trong một lần gọi theo trợ giúp của jdeps. Chọn một cách lọc phù hợp cho mỗi lệnh.

### Giới hạn class được phân tích

~~~bash
jdeps -include "com\.example\.app\..*" \
    -verbose:package \
    build/classes
~~~

-include giới hạn danh sách class được phân tích bằng regex. Khác với -p và -e, vốn lọc dependency được tìm thấy, -include chọn class nguồn được đưa vào phân tích.

### Lọc nội bộ

Các chế độ thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| -filter:package | Lọc dependency trong cùng package; mặc định |
| -filter:archive | Lọc dependency trong cùng archive |
| -filter:module | Lọc dependency trong cùng module |
| -filter:none | Không áp dụng các bộ lọc package/archive mặc định |

Ví dụ:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Dùng -filter:none khi cần xem cả quan hệ giữa các package trong cùng archive. Khi output quá lớn, trở lại bộ lọc mặc định hoặc giới hạn đầu vào bằng -include.

## 11. Phân tích dependency ngược

Thông thường, jdeps hiển thị package hoặc class nguồn phụ thuộc vào package hoặc class đích.

Đôi khi câu hỏi cần trả lời là: package nào đang sử dụng package này?

Có thể dùng --inverse kết hợp bộ lọc package, regex hoặc module:

~~~bash
jdeps --inverse --package java.sql \
    --recursive \
    build/classes
~~~

Lệnh này tìm các artifact phụ thuộc trực tiếp hoặc gián tiếp vào dependency khớp package java.sql, theo phạm vi phân tích đã chọn.

Ví dụ khác:

~~~bash
jdeps --inverse --require java.sql \
    --recursive \
    mlib
~~~

Inverse analysis hữu ích khi:

- Chuẩn bị thay thế một thư viện.
- Đánh giá ảnh hưởng khi xóa package.
- Tìm module hoặc archive đang phụ thuộc một API.
- Điều tra vì sao một dependency vẫn được kéo vào runtime.

--inverse phải được dùng cùng --require, --package hoặc --regex. Không dùng nó như một lệnh đảo đồ thị tùy ý mà không có tiêu chí tìm kiếm.

## 12. Tạo sơ đồ dependency bằng DOT

Có thể xuất graph để xem bằng Graphviz hoặc công cụ hỗ trợ DOT.

~~~bash
jdeps --dot-output build/dependency-graphs \
    -verbose:package \
    build/classes
~~~

jdeps tạo các file DOT trong thư mục chỉ định. Tên và số lượng file phụ thuộc đầu vào; thường có graph tổng hợp và graph cho từng archive.

Một đoạn DOT khái quát:

~~~dot
digraph "classes" {
    "com.example.app" -> "com.example.data";
    "com.example.app" -> "com.example.format";
    "com.example.data" -> "java.time";
    "com.example.format" -> "java.util";
}
~~~

Đây là minh họa cấu trúc, không phải nội dung file DOT cố định do jdeps phát ra. Graph thật có thể chứa node archive/module, package hoặc class tùy chế độ và đầu vào.

Có thể chuyển file DOT thành hình bằng Graphviz:

~~~bash
dot -Tpng build/dependency-graphs/classes.dot \
    -o build/dependency-graphs/classes.png
~~~

Nếu tên file DOT thực tế khác classes.dot, dùng đúng tên trong thư mục output. Với graph lớn, có thể lọc package hoặc class trước khi xuất để hình dễ đọc.

Sơ đồ giúp nhìn ra:

- Package có quá nhiều dependency đi ra.
- Package được nhiều thành phần phụ thuộc.
- Dependency vòng.
- Ranh giới package không rõ.
- Các package nội bộ đang bị sử dụng từ nhiều module.

jdeps phát hiện và hiển thị quan hệ; việc quyết định cách tái cấu trúc vẫn cần đánh giá thiết kế của ứng dụng.

## 13. Tìm dependency bị thiếu

Dùng --missing-deps để tìm dependency mà jdeps không thể phân giải:

~~~bash
jdeps --missing-deps build/classes
~~~

Nếu cần bỏ qua dependency thiếu trong một lần phân tích, có thể dùng:

~~~bash
jdeps --ignore-missing-deps -verbose:package build/classes
~~~

Không nên dùng --ignore-missing-deps để che giấu lỗi build hoặc kết luận rằng dependency đã đầy đủ. Hãy ghi nhận class nào không tìm thấy và bổ sung đúng JAR/module path nếu cần.

Một dependency thiếu có thể xuất hiện vì:

- JAR chưa có trên classpath.
- Module chưa có trên module path.
- Phiên bản dependency không chứa class được tham chiếu.
- Artifact bị đóng gói thiếu class.
- Phân tích một phần source tree mà không có các module còn lại.

Khi mục tiêu là audit hoặc migration, giữ warning và giải quyết nguyên nhân thay vì bỏ qua.

## 14. Tìm việc sử dụng JDK internal API

JDK có những package nội bộ không phải API công khai được cam kết tương thích. Ứng dụng dùng các class như sun.* hoặc jdk.internal.* có thể hỏng khi nâng cấp JDK.

jdeps hỗ trợ:

~~~bash
jdeps --jdk-internals build/classes
~~~

Tùy chọn này tìm class-level dependency tới JDK internal API. Ví dụ output có thể nêu class nội bộ được tham chiếu và module chứa nó.

Khi tìm thấy dependency:

1. Xác định API nội bộ đang được sử dụng.
2. Tìm API công khai thay thế trong Java SE hoặc API được hỗ trợ.
3. Thay implementation.
4. Biên dịch và chạy test trên JDK mục tiêu.
5. Chạy lại jdeps --jdk-internals để xác nhận.

Theo trợ giúp jdeps, --jdk-internals không dùng cùng -p, -e và -s. Hãy chạy riêng lệnh audit này.

Không nên dựa vào --add-exports như một giải pháp lâu dài cho ứng dụng sử dụng internal API. Tùy chọn đó có thể mở package trong một cấu hình runtime nhất định, nhưng không biến internal API thành API ổn định.

## 15. Chỉ phân tích dependency xuất hiện trong API công khai

Một thư viện có thể dùng nhiều package trong implementation, nhưng chỉ một phần trong số đó xuất hiện trong public/protected API.

Tùy chọn --api-only giới hạn phân tích vào dependency xuất hiện trong signature của public/protected member thuộc public class. Nó bao gồm kiểu field, tham số method, kiểu trả về và checked exception.

~~~bash
jdeps --api-only -verbose:package build/classes
~~~

So sánh với phân tích đầy đủ:

~~~bash
jdeps -verbose:package build/classes
~~~

Nếu một package chỉ được gọi trong method body, dependency đó có thể xuất hiện trong phân tích đầy đủ nhưng không xuất hiện trong API-only.

API-only hữu ích khi:

- Đánh giá dependency mà người dùng thư viện cần đọc.
- Thiết kế module descriptor.
- Xác định dependency có trở thành một phần hợp đồng public hay không.
- Phân tích khả năng thay đổi implementation mà không ảnh hưởng API.

Nó không thay thế kiểm tra binary compatibility. Một API có thể thay đổi theo cách gây lỗi tương thích dù dependency package graph không thay đổi.

## 16. Dependency package và dependency module

Package và module là hai cấp tổ chức khác nhau:

- Package gom class có namespace chung.
- Module gom package và khai báo dependency, export, open, service.
- Một module có thể chứa nhiều package.
- Một package trong named module không tự động được export.

Ví dụ module com.example.app có thể chứa:

~~~text
com.example.app
├── com.example.app
├── com.example.app.cli
└── com.example.app.internal
~~~

Module descriptor khai báo:

~~~java
module com.example.app {
    requires com.example.data;
    exports com.example.app;
}
~~~

jdeps package analysis cho thấy package nào tham chiếu package nào. Module analysis cho thấy module cần module nào. Một module dependency có thể phát sinh từ nhiều package dependency bên trong.

Không suy luận rằng package được tham chiếu đồng nghĩa package đã được export đúng cách. Trong JPMS, readability và exports vẫn phải được đáp ứng khi biên dịch/chạy.

## 17. Hỗ trợ migration thư viện sang JPMS

Thư viện cũ có thể chưa có module-info.class. jdeps giúp khảo sát dependency trước khi thêm descriptor.

Có thể yêu cầu jdeps tạo gợi ý module descriptor:

~~~bash
jdeps --generate-module-info build/module-info \
    lib/legacy-library.jar
~~~

Với thư viện cần open module:

~~~bash
jdeps --generate-open-module build/module-info \
    lib/legacy-library.jar
~~~

Công cụ tạo module-info.java dưới thư mục được chỉ định dựa trên dependency mà nó phân tích được.

Đây là điểm bắt đầu cho migration, không phải descriptor hoàn chỉnh được đảm bảo đúng kiến trúc. Sau khi tạo, cần review:

- Tên module có ổn định và đúng quy ước không.
- requires có dependency nào không cần thiết không.
- requires transitive có thực sự cần cho public API không.
- Package nào nên exports.
- Có package cần opens cho framework reflection không.
- uses/provides có cần khai báo không.
- Dependency động có bị bỏ sót không.
- Descriptor có compile và chạy được trên JDK mục tiêu không.

--generate-module-info và --generate-open-module phân tích JAR được chỉ định. Theo trợ giúp công cụ, các tùy chọn này không kết hợp với --dot-output hoặc --class-path trong cùng lần gọi. Hãy kiểm tra jdeps --help của JDK đang sử dụng.

## 18. Multi-release JAR và chọn phiên bản

Một multi-release JAR có thể chứa nhiều bản class theo release Java. Khi phân tích, cần chọn góc nhìn phù hợp.

~~~bash
jdeps --multi-release base -verbose:package lib/library.jar
~~~

Hoặc chọn release cụ thể:

~~~bash
jdeps --multi-release 17 -verbose:package lib/library.jar
~~~

--multi-release nhận base hoặc số nguyên từ 9 trở lên. Điều này giúp phân tích các class thực tế mà một runtime release sẽ nhìn thấy trong MR-JAR.

Nếu không chọn đúng release, dependency được báo cáo có thể không phản ánh implementation mà runtime mục tiêu sử dụng.

## 19. Đưa jdeps vào quy trình build và CI

jdeps hữu ích như một bước audit sau compile hoặc đóng gói.

Một pipeline đơn giản:

1. Compile source thành class file.
2. Chạy unit test.
3. Chạy jdeps -verbose:package để xem package dependency.
4. Chạy jdeps --missing-deps để tìm class không phân giải được.
5. Chạy jdeps --jdk-internals để tìm internal API.
6. Với modular app, chạy --list-deps hoặc --print-module-deps.
7. Lưu DOT graph làm artifact nếu cần review kiến trúc.
8. So sánh kết quả với dependency baseline của dự án.

Ví dụ các lệnh:

~~~bash
jdeps -verbose:package -filter:none build/classes

jdeps --missing-deps build/classes

jdeps --jdk-internals build/classes

jdeps --print-module-deps --module-path mlib \
    --module com.example.app
~~~

Nếu đưa vào CI, có thể lưu output để so sánh giữa các lần build. jdeps không tự áp dụng chính sách kiến trúc của dự án; pipeline cần có quy tắc riêng để quyết định package dependency nào được phép.

Ví dụ, một module domain có thể bị cấm phụ thuộc vào package web hoặc persistence. Có thể dùng output jdeps và script kiểm tra để phát hiện khi có cạnh dependency vi phạm quy tắc.

Không nên coi mọi dependency mới là lỗi. Đánh giá dependency theo kiến trúc, API và yêu cầu vận hành trước khi chặn build.

## 20. Giới hạn của phân tích tĩnh

jdeps phân tích các tham chiếu thể hiện trong bytecode. Một số dependency có thể không xuất hiện trong kết quả:

- Class được nạp qua Class.forName với tên class lấy từ cấu hình.
- Reflection dựa trên tên method/field.
- Service provider được chọn từ file cấu hình hoặc runtime environment.
- Class được tạo hoặc tải qua custom class loader.
- Mã native gọi vào Java hoặc ngược lại.
- Dependency được tạo ra từ code generation sau bước phân tích.
- Tài nguyên hoặc script chứa tên class mà bytecode không tham chiếu trực tiếp.

Do đó, kết quả jdeps là bản đồ dependency tĩnh, không phải bằng chứng tuyệt đối về mọi class sẽ được dùng lúc chạy.

Để tăng độ tin cậy, kết hợp:

- Phân tích source và module descriptor.
- Kiểm tra cấu hình framework.
- Integration test trên môi trường triển khai.
- Runtime tracing hoặc logging khi cần.
- Review service loader và reflection configuration.
- Kiểm tra nội dung JAR cuối cùng thay vì chỉ source tree.

## 21. Các lỗi thường gặp

**Không tìm thấy class hoặc dependency**

Bổ sung đúng classpath/module path. Kiểm tra JAR có chứa class và phiên bản dependency có tương thích không.

**Output quá lớn**

Chuyển từ -verbose:class sang -verbose:package hoặc -summary. Dùng -include, -p hoặc -e để giới hạn phạm vi.

**Không thấy dependency nội bộ**

Bộ lọc mặc định có thể ẩn quan hệ trong cùng package/archive. Thử -filter:none.

**Nhầm package dependency với module dependency**

Package dependency thể hiện quan hệ giữa package. Module dependency thể hiện quan hệ giữa module. Dùng đúng chế độ phân tích cho câu hỏi cần trả lời.

**Dependency reflection không xuất hiện**

jdeps không thể suy ra đầy đủ tên class được tạo từ chuỗi hoặc cấu hình. Kiểm tra framework và runtime configuration.

**Không hiểu vì sao java.base xuất hiện nhiều lần**

java.base chứa nhiều package nền tảng như java.lang, java.io, java.time và java.util. Các package trong module này có thể được tham chiếu từ nhiều package ứng dụng.

**--jdk-internals không chạy cùng bộ lọc**

Tùy chọn này không kết hợp với -p, -e và -s theo trợ giúp jdeps. Chạy audit internal API riêng.

**--print-module-deps không hiển thị package**

Đây là output cấp module, không phải package. Dùng -verbose:package nếu cần dependency giữa package.

**DOT graph không tạo đúng hình**

Kiểm tra đường dẫn file .dot thực tế và cú pháp Graphviz. jdeps tạo DOT; Graphviz hoặc công cụ tương đương chịu trách nhiệm render hình.

## 22. Quy trình phân tích dependency package

1. Build class file hoặc xác định JAR cần phân tích.
2. Cung cấp đầy đủ classpath/module path cho dependency bên ngoài.
3. Chạy -verbose:package để xem package-level dependency.
4. Dùng -filter:none nếu cần cả quan hệ nội bộ.
5. Dùng -verbose:class khi cần truy vết class cụ thể.
6. Dùng -summary để có cái nhìn ở cấp archive/module.
7. Dùng --recursive khi cần phân tích dependency bắc cầu.
8. Dùng --inverse khi muốn tìm artifact phụ thuộc vào package/module mục tiêu.
9. Dùng --missing-deps và --jdk-internals để audit.
10. Dùng --api-only để phân tích dependency trong public API.
11. Dùng --dot-output khi cần trực quan hóa graph.
12. Với modular app, kiểm tra --list-deps, --check và --print-module-deps.
13. Đối chiếu kết quả với kiến trúc mong muốn và kiểm thử runtime.

jdeps giúp biến các tham chiếu trong bytecode thành bản đồ dependency có thể đọc và phân tích. Khi chọn đúng cấp package, class hoặc module, cung cấp đủ đường dẫn dependency và hiểu giới hạn của phân tích tĩnh, developer có thể dùng công cụ này để kiểm tra kiến trúc, chuẩn bị migration JPMS và giảm rủi ro khi thay đổi thư viện.

## Tài liệu tham khảo

- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
- [jdeps tool documentation — Oracle Java Platform](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
