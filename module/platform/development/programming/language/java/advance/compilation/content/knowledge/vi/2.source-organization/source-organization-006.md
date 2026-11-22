# Vai trò của package-info.java và module-info.java trong tổ chức mã nguồn Java

Trong Java, **package** gom các kiểu có liên quan thành một không gian tên; **module** (Java Platform Module System – JPMS, từ Java 9) gom các package thành một đơn vị có khai báo phụ thuộc và ranh giới truy cập. Hai tệp đặc biệt **package-info.java** và **module-info.java** mô tả hai cấp tổ chức này. Chúng bổ sung metadata vào mã nguồn, nhưng giải quyết những vấn đề khác nhau.

## 1. Phân biệt nhanh

| Tiêu chí | package-info.java | module-info.java |
| --- | --- | --- |
| Gắn với | Một package, ví dụ com.example.math | Một named module, ví dụ com.example.math |
| Vị trí | Cùng thư mục nguồn với các lớp thuộc package | Gốc thư mục nguồn của module |
| Nội dung chính | Javadoc cấp package, annotation áp dụng cho package | Khai báo module, phụ thuộc và ranh giới API, reflection, dịch vụ |
| Tác động chủ yếu | Tài liệu và metadata cho công cụ/thư viện | Cơ chế đọc module, kiểm tra truy cập, cấu hình runtime của JPMS |
| Bắt buộc? | Không | Cần để khai báo một explicit named module; ứng dụng chạy trên classpath không cần |
| Có thay thế nhau? | Không | Không |

**Một package không phải một module.** Một module thường chứa nhiều package. Mỗi package có thể có tệp package-info.java riêng, trong khi mỗi explicit named module có một module-info.java ở gốc nguồn. Tên package không bắt buộc trùng tên module.

## 2. package-info.java: tài liệu và annotation cho một package

### 2.1. Viết tài liệu cấp package

**package-info.java** là nơi chuẩn để viết Javadoc giải thích trách nhiệm của package, hợp đồng API, quy ước sử dụng và mối quan hệ giữa các kiểu trong package. Ví dụ:

~~~java
// src/com.example.math/com/example/math/package-info.java
/**
 * Cung cấp các phép toán số học dùng chung cho ứng dụng.
 *
 * <p>Những lớp công khai ở đây là API ổn định của package.
 * Các thao tác có thể ném ArithmeticException khi tràn số.
 */
package com.example.math;
~~~

Cụm chú thích Javadoc nằm **ngay trước khai báo package**, có thể cách bởi annotation cấp package. Công cụ Javadoc lấy phần mô tả này làm tài liệu package; một tệp Java bất kỳ chứa nhiều chú thích trên lớp không tự thay thế được vai trò mô tả package.

Tài liệu nên nói về **trách nhiệm và hợp đồng chung** của package; mô tả đặc thù của từng lớp/phương thức vẫn đặt tại lớp/phương thức ấy. Đổi tên package hoặc di chuyển lớp cần xem lại tài liệu để tránh mô tả sai phạm vi.

### 2.2. Khai báo annotation ở cấp package

Một annotation có **@Target(ElementType.PACKAGE)** có thể đặt vào khai báo package. Ví dụ, giả sử có annotation **PackagePurpose** với **@Retention(RetentionPolicy.RUNTIME)**:

~~~java
/** Package cung cấp các API phép tính. */
@PackagePurpose("math-api")
package com.example.math;
~~~

Annotation được đặt **trước từ khóa package**, không đặt vào một lớp bất kỳ. Khi biên dịch, compiler có thể tạo **package-info.class** chứa metadata annotation; các framework/công cụ hoặc mã reflection có thể đọc thông tin này. Annotation phải được định nghĩa hợp lệ và có phạm vi truy cập phù hợp; ví dụ hoàn chỉnh ở phần 4.

Một cách dùng thực tế là annotation quy ước nullability, mặc định cấu hình mapping hoặc phân loại package do thư viện hỗ trợ. **Bản thân một annotation không tự áp đặt kiểm tra null hay quy tắc nghiệp vụ**: phải có compiler, annotation processor, static analyzer hoặc framework thực sự đọc và diễn giải nó. Với annotation chỉ giữ ở SOURCE/CLASS, reflection tại runtime không thể tự đọc như annotation RUNTIME.

### 2.3. Quy tắc và giới hạn

- Tên tệp là **package-info.java** và khai báo package phải khớp đường dẫn/kiểu bố trí nguồn mà build dùng. Thường chỉ có một khai báo package-info cho mỗi package trong cùng một bộ source khi biên dịch.
- Tệp thường chỉ chứa package declaration, Javadoc, package annotations và import cần thiết; không dùng nó như nơi đặt các lớp nghiệp vụ.
- Chỉ thêm **package-info.java** không làm package thành public, không tự tạo module, không thay đổi quyền truy cập của class hay method.
- Package không có metadata cần mô tả có thể không cần tệp này. Không nên viết tệp chỉ để đủ hình thức.
- Nếu chỉ có Javadoc mà không có annotation cần giữ trong bytecode, việc có hay không có **package-info.class** tùy cách biên dịch; **tệp .java mới là nguồn tài liệu**, không nên dựa vào sự tồn tại của class file.

## 3. module-info.java: hợp đồng module trong JPMS

### 3.1. Khai báo module và phụ thuộc

Tệp **module-info.java** đặt tại gốc source của một module và có cấu trúc khai báo, ví dụ:

~~~java
module com.example.app {
    requires com.example.math;
}
~~~

Tên **com.example.app** là tên module. **requires** khai báo module app đọc module math để truy cập những public type mà math cho phép xuất. **java.base** được mọi module đọc mặc định, không cần viết requires java.base.

JPMS giúp trình biên dịch và module system xác thực các quan hệ đọc và khả năng truy cập của package, phát hiện một số thiếu phụ thuộc hoặc xung đột cấu hình từ sớm. Khi chạy trên **module path**, module-info.class cung cấp descriptor cho runtime. Không có module-info.java thì mã nguồn vẫn có thể được biên dịch/chạy theo mô hình classpath truyền thống.

### 3.2. Các chỉ thị quan trọng

| Chỉ thị | Ý nghĩa và tình huống |
| --- | --- |
| **requires other.module;** | Module hiện tại đọc module được chỉ định. |
| **requires transitive other.module;** | Module phụ thuộc và chuyển tiếp khả năng đọc tới module khác đọc module hiện tại; hữu ích khi public API bộc lộ kiểu của phụ thuộc. Không tự xuất mọi package. |
| **requires static other.module;** | Phụ thuộc cần ở compile time nhưng có thể vắng ở runtime; mã thực thi phải chịu được sự vắng mặt khi thực sự sử dụng tính năng. |
| **exports some.pkg;** | Cho phép các module khác truy cập public type của package bằng cơ chế thông thường, nếu có quan hệ đọc thích hợp. |
| **exports some.pkg to client.module;** | Chỉ xuất package cho các module được nêu tên. |
| **opens some.pkg;** | Cho phép deep reflection vào package tại runtime, ví dụ framework cần truy cập thành viên không public. Không cấp quyền import thông thường khi biên dịch. |
| **opens some.pkg to framework.module;** | Chỉ mở reflective access cho các module đích. |
| **uses some.Service;** | Công bố module tiêu thụ service thông qua ServiceLoader. |
| **provides some.Service with some.Impl;** | Đăng ký implementation của service để service loader tìm được. |

Có thể khai báo **open module tên.module { ... }** để mở mọi package của module cho deep reflection, nhưng thường nên mở đúng package cần thiết. Một package có thể vừa **exports** (API compile time) vừa **opens** (reflection runtime); hai ý nghĩa độc lập. **exports** cũng không làm cho class package-private trở thành public và không cho phép truy cập mọi private field.

### 3.3. Encapsulation ở mức module

Giả sử **com.example.math** chứa **com.example.math** (API công khai) và **com.example.math.internal** (implementation). Khi module chỉ có:

~~~java
module com.example.math {
    exports com.example.math;
}
~~~

Module khác có quan hệ đọc có thể dùng các **public class** trong package xuất khẩu **com.example.math**, nhưng không thể import trực tiếp kiểu ở **com.example.math.internal** qua biên giới module. Kể cả một lớp trong internal được khai báo public, **public không đồng nghĩa package đã được exports**.

Khi framework serialization/DI cần truy cập qua reflection vào thành viên không public của package internal, có thể cân nhắc:

~~~java
module com.example.math {
    exports com.example.math;
    opens com.example.math.internal to some.framework;
}
~~~

Đoạn này **minh họa cú pháp**, chỉ dùng khi **some.framework** là tên module thực tế của framework được sử dụng. Nếu framework chỉ cần gọi public API, không mở package vô cớ. Khi chuyển ứng dụng cũ từ classpath sang module path, lỗi **IllegalAccessException** hoặc **InaccessibleObjectException** thường liên quan đến khác biệt giữa exports, opens và quyền truy cập Java thông thường.

## 4. Ví dụ Java 17+: kết hợp cả hai tệp, biên dịch và chạy

Ví dụ có **hai module**: com.example.math cung cấp API; com.example.app sử dụng API đó. Package của math có Javadoc và một annotation runtime do chúng ta định nghĩa. Cấu trúc thư mục:

~~~text
src/
├── com.example.math/
│   ├── module-info.java
│   └── com/example/math/
│       ├── package-info.java
│       ├── PackagePurpose.java
│       └── Calculator.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        └── Main.java
~~~

**Tệp 1 — src/com.example.math/module-info.java:**

~~~java
module com.example.math {
    exports com.example.math;
}
~~~

Math công bố package API để app có thể sử dụng. Không cần requires java.base.

**Tệp 2 — src/com.example.math/com/example/math/PackagePurpose.java:**

~~~java
package com.example.math;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePurpose {
    String value();
}
~~~

Đây là annotation do ví dụ định nghĩa, áp dụng cho **PACKAGE** và giữ tại runtime. Khai báo public để code của module app có thể tham chiếu kiểu annotation.

**Tệp 3 — src/com.example.math/com/example/math/package-info.java:**

~~~java
/**
 * Cung cấp các phép toán đơn giản cho ứng dụng khác.
 *
 * <p>API công khai của module {@code com.example.math}.
 */
@PackagePurpose("math-api")
package com.example.math;
~~~

Package được mô tả bằng Javadoc và gắn annotation. Compiler sẽ phát ra metadata cần thiết để đọc annotation bằng reflection.

**Tệp 4 — src/com.example.math/com/example/math/Calculator.java:**

~~~java
package com.example.math;

public final class Calculator {
    private Calculator() {}

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

**Tệp 5 — src/com.example.app/module-info.java:**

~~~java
module com.example.app {
    requires com.example.math;
}
~~~

**Tệp 6 — src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import com.example.math.Calculator;
import com.example.math.PackagePurpose;

public class Main {
    public static void main(String[] args) {
        System.out.println(Calculator.add(2, 3));

        PackagePurpose purpose = Calculator.class.getPackage()
                .getAnnotation(PackagePurpose.class);
        System.out.println(purpose.value());
    }
}
~~~

Từ thư mục **chứa src**, chạy bằng JDK 17+:

~~~bash
javac -d out --module-source-path src -m com.example.math,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

**Đầu ra chuẩn:**

~~~text
5
math-api
~~~

Lệnh javac biên dịch các module được nêu, ghi class/module descriptor vào **out**. Lệnh java dùng **--module-path** để tìm module và **-m module/main.class** để chạy điểm vào. Gọi **Calculator.class.getPackage().getAnnotation(...)** cho thấy annotation cấp package được giữ và tra cứu đúng ở runtime.

Thử thay **exports com.example.math;** bằng không xuất package rồi biên dịch lại: app vẫn khai báo requires, nhưng import Calculator/PackagePurpose từ package không được exports sẽ bị compiler từ chối. Đó là khác biệt rõ nhất giữa **đọc module** và **quyền truy cập package**.

## 5. Chọn tệp nào trong dự án thực tế?

| Nhu cầu | Giải pháp |
| --- | --- |
| Giải thích mục đích và cách dùng của một nhóm API cùng package | Viết Javadoc trong package-info.java |
| Áp dụng annotation mặc định cho cả package với thư viện hỗ trợ | Đặt annotation trong package-info.java |
| Tạo module có tên và chỉ rõ module phụ thuộc | Tạo module-info.java với requires |
| Công bố đúng những package tạo API công khai | Dùng exports trong module-info.java |
| Cho framework thực hiện deep reflection trên package cụ thể | Dùng opens thích hợp trong module-info.java |
| Chia nhỏ class theo namespace mà chưa dùng JPMS | Tổ chức package bình thường; module-info.java chưa bắt buộc |
| Cần cả tài liệu package và ranh giới module | Dùng cả hai, ở hai vị trí khác nhau |

Trong dự án Maven/Gradle, vẫn giữ cấu trúc nguồn chuẩn của công cụ build; với module JPMS, thường đặt **module-info.java** tại gốc source set tương ứng (ví dụ **src/main/java** của từng project/module) và package-info.java trong thư mục package. Cách đặt nhiều module chung một source root như phần 4 phù hợp để minh họa lệnh javac; không bắt buộc mọi dự án phải có cấu trúc như vậy.

Khi đóng gói named module thành JAR, **module-info.class** nằm ở gốc JAR. Cấu hình dependency của Maven/Gradle và khai báo **requires** trong JPMS phục vụ hai lớp quản lý khác nhau: build tool lấy artifact; module system xác lập quan hệ giữa module khi biên dịch/chạy. Có dependency trong Gradle chưa có nghĩa automatically khai báo requires phù hợp cho named module.

## 6. Lỗi phổ biến và cách kiểm tra

1. **Nhầm package với module.** Khai báo package của lớp chỉ xác định namespace; không tự tạo descriptor JPMS. Một module có thể chứa nhiều package và export một phần trong số đó.
2. **Đặt module-info.java sai chỗ.** Descriptor phải ở gốc source của module tương ứng; đặt dưới một package khiến cấu trúc không hợp lệ.
3. **Thiếu requires hoặc exports.** requires cho phép đọc module, exports cho phép các module đọc truy cập public API của package. Thiếu một trong hai đều có thể gây lỗi biên dịch.
4. **Nhầm opens với exports.** opens chỉ hỗ trợ reflective access ở runtime. Để code Java khác import trực tiếp public class, cần exports và requires phù hợp.
5. **Cho rằng package-info.java áp đặt quy tắc tự động.** Annotation chỉ là metadata; mức ảnh hưởng phụ thuộc công cụ đọc annotation và chính sách retention.
6. **Quên đường dẫn hoặc package declaration.** Ví dụ file trong com/example/math phải khai báo package com.example.math; cấu trúc module source path của ví dụ phải khớp tên module.
7. **Dùng classpath và module path lẫn lộn.** JAR trên classpath thuộc unnamed module và không nhận cùng cơ chế encapsulation như explicit named module. Cần kiểm tra project đang chạy theo kiểu nào trước khi kỳ vọng module-info có hiệu lực.
8. **Đưa cùng package vào nhiều named module đã được resolve.** Cấu hình gây split-package có thể lỗi phân giải module hoặc lúc tạo module layer; thiết kế module nên phân định package rõ ràng.
9. **Mở mọi package để sửa lỗi reflection.** Dùng opens đúng package và đúng module consumer; chỉ dùng tùy chọn dòng lệnh như **--add-opens** cho trường hợp chuyển đổi có chủ đích.
10. **Giả định annotation package luôn có ở runtime.** Chỉ annotation được giữ với RetentionPolicy.RUNTIME mới tra cứu được qua reflection theo cách phần 4.

Để kiểm tra descriptor sau khi biên dịch, có thể dùng:

~~~bash
java --module-path out --describe-module com.example.math
~~~

Lệnh này trình bày thông tin module đã biên dịch, gồm các package xuất; nội dung và cách sắp xếp từng dòng có thể thay đổi theo JDK, nên không gán một stdout cố định. Tài liệu package có thể sinh bằng **javadoc** theo cấu trúc nguồn tương ứng.

## 7. Câu hỏi tự kiểm tra

- Nếu một thư viện có ba package nhưng chỉ hai package là public API, bạn sẽ cấu hình exports ở đâu và vì sao?
- Nếu một framework chỉ cần đọc private fields qua reflection, exports có đủ hay cần opens?
- Khi package-info.java gắn @Target(PACKAGE) annotation nhưng thiếu @Retention(RUNTIME), điều gì xảy ra nếu dùng getAnnotation tại runtime?
- Vì sao app trong ví dụ phải có cả requires com.example.math và math phải exports com.example.math?
- Trong ứng dụng còn chạy trên classpath, khi nào package-info.java vẫn hữu ích dù không tạo module-info.java?

**Ghi nhớ:** **package-info.java** giải thích và gắn metadata cho một **package**; **module-info.java** mô tả phụ thuộc, API bộc lộ và quyền reflection của một **module**. Dùng cả hai khi muốn mã nguồn vừa có tài liệu đúng cấp vừa có ranh giới module rõ ràng.