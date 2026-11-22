# Annotation trên package qua package-info.java

## Khái niệm và mục đích

Một annotation không nhất thiết chỉ gắn vào lớp hoặc phương thức. Java cho phép gắn annotation vào **khai báo package**, nhờ đó công cụ có thể đọc siêu dữ liệu chung của package mà không phải lặp cùng một thông tin trên từng lớp.

`package-info.java` là tệp nguồn chuyên dùng cho tài liệu và annotation ở cấp package. Nó vẫn được sử dụng trong Java hiện đại. Tệp thường đặt cùng thư mục nguồn với các lớp của package tương ứng.

Cần phân biệt ba tầng:

- **Package:** không gian tên chứa các kiểu Java, ví dụ `learn.model`.
- **Tệp `package-info.java`:** nơi viết tài liệu và annotation cho package ấy.
- **Thành phần đọc annotation:** trình biên dịch, công cụ phân tích, bộ xử lý annotation hoặc mã chạy dùng reflection để diễn giải siêu dữ liệu.

Annotation chỉ cung cấp thông tin. Nó không tự tạo hành vi, thay đổi quyền truy cập hoặc áp đặt quy tắc cho mọi lớp trong package.

Một trường hợp sử dụng dễ hiểu là ghi nhận tầng kiến trúc và nhóm phụ trách của package. Công cụ nội bộ có thể đọc các giá trị đó để lập báo cáo hoặc kiểm tra quy ước. Nếu không có thành phần đọc và áp dụng, annotation chỉ là siêu dữ liệu.

## Cấu trúc của package-info.java

Dạng minh họa:

```java
/**
 * Tài liệu chung của package.
 */
@PackagePolicy(layer = "domain", owner = "training")
package learn.model;

import learn.meta.PackagePolicy;
```

Trong cấu trúc này:

1. Khối Javadoc mô tả package.
2. Annotation đứng **trước** câu lệnh `package`.
3. Câu lệnh `package learn.model;` chỉ rõ package được gắn annotation.
4. Các `import` vẫn đứng sau khai báo package theo cấu trúc tệp Java thông thường.

Dù `import` xuất hiện sau khai báo package, tên kiểu annotation được import vẫn có thể dùng cho annotation trên khai báo package của cùng tệp.

Không tạo một lớp tên `package-info`. Tệp này không cần `main`, constructor hay một lớp public để làm nhiệm vụ của nó. Nên giữ phần thân tệp tập trung vào tài liệu và annotation cấp package.

Khai báo annotation của package trong `package-info.java`, thay vì rải trên các khai báo package của nhiều tệp lớp khác nhau. Đặc tả đặt ràng buộc đối với số khai báo package được gắn annotation và hướng việc tổ chức chúng vào tệp này; xem [JLS §7.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.4.1).

## Điều kiện để một annotation dùng được trên package

### Target phải cho phép PACKAGE

Một kiểu annotation giới hạn vị trí sử dụng bằng `@Target` phải bao gồm `ElementType.PACKAGE` nếu muốn dùng trên khai báo package.

Ví dụ:

```java
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String layer();
    String owner();
}
```

Đây chỉ là phần khai báo minh họa; ví dụ đầy đủ bên dưới có toàn bộ import và chính sách lưu giữ.

Nếu kiểu annotation chỉ cho phép `ElementType.TYPE`, không thể đưa nó vào `package-info.java` rồi mặc nhiên dùng như annotation của package. `TYPE` và `PACKAGE` là hai đích khác nhau.

Một kiểu annotation có thể cho phép nhiều đích, nhưng việc cho phép nhiều nơi sử dụng không làm các annotation ở những nơi đó tự đồng bộ với nhau.

Định nghĩa từng đích có trong [ElementType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html).

### Retention phải phù hợp với thời điểm đọc

| Chính sách lưu giữ | Hệ quả đối với việc đọc annotation |
| --- | --- |
| `SOURCE` | Dùng ở giai đoạn xử lý nguồn; không giữ annotation trong tệp class |
| `CLASS` | Giữ annotation trong tệp class; reflection lúc chạy không đọc theo cách thông thường |
| `RUNTIME` | Có thể đọc bằng reflection lúc chạy |

Nếu không khai báo `@Retention`, mặc định là `CLASS`. Vì ví dụ trong bài cần đọc bằng `Package.getAnnotation`, kiểu annotation sẽ dùng `RUNTIME`.

`@Documented` là một lựa chọn khác: nó cho biết việc sử dụng annotation được đưa vào tài liệu API theo công cụ hỗ trợ. Nó không thay cho `@Retention(RUNTIME)` và không làm annotation tự có hiệu lực nghiệp vụ.

## Annotation của package không phải annotation của mọi lớp

Giả sử `learn.model` có `@PackagePolicy`:

- `Customer.class.getPackage().getAnnotation(PackagePolicy.class)` đọc annotation của package chứa `Customer`.
- `Customer.class.getAnnotation(PackagePolicy.class)` đọc annotation của chính lớp `Customer`.

Đó là hai phần tử phản chiếu khác nhau. Việc package có annotation không khiến mỗi lớp tự mang một bản sao annotation ấy.

Một công cụ có thể quy định “nếu lớp không tự khai báo cấu hình thì đọc cấu hình của package”, nhưng đó là quy tắc do công cụ thiết kế. Java không tự thực hiện mọi dạng tìm cấu hình như vậy.

Tương tự, một annotation biểu thị giá trị mặc định ở cấp package chỉ tác động đến phân tích kiểu, kiểm tra dữ liệu hoặc sinh mã nếu hệ công cụ tương ứng định nghĩa và thực hiện ngữ nghĩa đó. Chỉ viết annotation không tự thêm kiểm tra `null` hoặc kiểm tra đầu vào vào các phương thức.

## Package con là một package riêng

`learn.model` và `learn.model.order` có tên liên quan nhưng là hai package riêng.

Annotation của `learn.model` không tự xuất hiện trên `learn.model.order`. Nếu muốn package con có cùng annotation, cần khai báo `package-info.java` riêng cho package con hoặc sử dụng một công cụ có quy tắc mặc định được định nghĩa rõ.

`@Inherited` cũng không tạo việc truyền annotation giữa package cha và package con. Cơ chế đó dành cho tra cứu annotation qua chuỗi lớp cha trong những trường hợp được Java quy định, không dành cho cấu trúc tên package.

Tính độc lập này còn giúp tránh hiểu nhầm rằng một annotation của package cha có thể tự thay đổi quyền truy cập ở tất cả package con.

## Ví dụ đầy đủ: khai báo, biên dịch và đọc annotation

Ví dụ dùng năm tệp nguồn, JDK 17 trở lên, không có thư viện ngoài và không cần module descriptor.

### Cây thư mục

```text
project/
└── src/
    └── learn/
        ├── meta/
        │   └── PackagePolicy.java
        ├── model/
        │   ├── package-info.java
        │   ├── Customer.java
        │   └── order/
        │       └── Order.java
        └── app/
            └── Main.java
```

### 1. Khai báo kiểu annotation

Tệp `src/learn/meta/PackagePolicy.java`:

```java
package learn.meta;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String layer();
    String owner();
}
```

Đặt kiểu annotation trong package `learn.meta` giúp ví dụ thể hiện rõ việc import khi dùng nó ở package khác. Kiểu annotation là `public` để có thể được sử dụng từ các package đó.

### 2. Gắn annotation vào package

Tệp `src/learn/model/package-info.java`:

```java
/**
 * Các kiểu mô hình của ví dụ.
 * Siêu dữ liệu mô tả tầng kiến trúc và nhóm phụ trách package.
 */
@PackagePolicy(layer = "domain", owner = "training")
package learn.model;

import learn.meta.PackagePolicy;
```

Annotation gắn vào `learn.model`, không gắn vào một lớp ngầm định tên `package-info`.

### 3. Tạo lớp đại diện trong package đã được gắn annotation

Tệp `src/learn/model/Customer.java`:

```java
package learn.model;

public final class Customer {
}
```

Lớp này không cần tự khai báo `@PackagePolicy`. Ta sẽ dùng đối tượng `Class` của nó làm mốc để lấy đúng đối tượng `Package`.

### 4. Tạo lớp ở package con chưa có annotation

Tệp `src/learn/model/order/Order.java`:

```java
package learn.model.order;

public final class Order {
}
```

Không tạo `package-info.java` cho `learn.model.order` trong ví dụ ban đầu. Điều này giúp quan sát rằng annotation không tự lan xuống package con.

### 5. Đọc bằng reflection

Tệp `src/learn/app/Main.java`:

```java
package learn.app;

import learn.meta.PackagePolicy;
import learn.model.Customer;
import learn.model.order.Order;

public class Main {
    public static void main(String[] args) {
        Package modelPackage = Customer.class.getPackage();
        PackagePolicy policy =
                modelPackage.getAnnotation(PackagePolicy.class);

        System.out.println("package=" + modelPackage.getName());
        System.out.println("layer="
                + (policy == null ? "none" : policy.layer()));
        System.out.println("owner="
                + (policy == null ? "none" : policy.owner()));
        System.out.println("class.policy="
                + Customer.class.isAnnotationPresent(PackagePolicy.class));

        Package orderPackage = Order.class.getPackage();
        System.out.println("subpackage=" + orderPackage.getName());
        System.out.println("subpackage.policy="
                + orderPackage.isAnnotationPresent(PackagePolicy.class));
    }
}
```

`Package` thuộc `java.lang`, nên không cần import riêng.

Điểm bắt đầu là `Customer.class.getPackage()`, sau đó mới gọi `getAnnotation` trên đối tượng package. Với các lớp thuộc package có tên trong ví dụ, cách này gắn phép tra cứu vào đúng lớp đại diện.

Mã xử lý khả năng `getAnnotation` trả `null`, thay vì giả định môi trường nào cũng đóng gói annotation đầy đủ.

### Biên dịch và chạy

Đứng trong thư mục `project`, chạy lệnh sau trên một dòng:

```shell
javac -encoding UTF-8 -d out src/learn/meta/PackagePolicy.java src/learn/model/package-info.java src/learn/model/Customer.java src/learn/model/order/Order.java src/learn/app/Main.java
java -cp out learn.app.Main
```

Không bỏ `package-info.java` khỏi danh sách nguồn. Ví dụ ghi rõ từng tệp để việc tái tạo không phụ thuộc vào cách một IDE tự tìm nguồn.

Kết quả:

```text
package=learn.model
layer=domain
owner=training
class.policy=false
subpackage=learn.model.order
subpackage.policy=false
```

### Giải thích kết quả

- `package=learn.model` xác nhận đang đọc package của `Customer`.
- `layer=domain` và `owner=training` đến từ annotation trên khai báo package trong `package-info.java`.
- `class.policy=false` cho thấy annotation của package không biến thành annotation trực tiếp của `Customer`.
- `subpackage=learn.model.order` xác nhận `Order` thuộc một package khác.
- `subpackage.policy=false` cho thấy annotation không tự truyền từ `learn.model` sang package con.

Nếu đổi `RetentionPolicy.RUNTIME` thành `RetentionPolicy.CLASS`, biên dịch lại đầy đủ rồi chạy, tên hai package vẫn như cũ, nhưng `layer` và `owner` sẽ là `none`. Lý do là annotation không còn đọc được qua reflection lúc chạy.

## Từ package-info.java đến package-info.class

Với annotation trong ví dụ, quá trình biên dịch tạo `out/learn/model/package-info.class`. Annotation của package khi chạy được đọc từ tệp class tương ứng, không được đọc trực tiếp từ tệp `.java` trong thư mục nguồn.

Chuỗi dữ liệu cần giữ đúng là:

```text
package-info.java
        |
        | javac
        v
package-info.class
        |
        | nam trong dau ra build / JAR
        v
Package.getAnnotation(...)
```

Vì vậy, việc IDE nhìn thấy annotation trong mã nguồn không đủ chứng minh một ứng dụng đã đóng gói đọc được annotation đó.

Khi tạo JAR, cần bảo đảm `package-info.class` đi cùng các lớp của package tại đúng vị trí. Ví dụ, sau lệnh biên dịch ở trên:

```shell
jar --create --file app.jar -C out .
java -cp app.jar learn.app.Main
```

Kết quả phải giống khi chạy từ thư mục `out`.

API [Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html) mô tả annotation của package lúc chạy được đọc từ `package-info.class` ở cùng nguồn mã với các lớp trong package đó.

Trong ứng dụng dùng nhiều bộ nạp lớp (class loader), cùng chuỗi tên package có thể gắn với những ngữ cảnh lúc chạy khác nhau. Khi đã có một lớp đại diện, nên đi từ lớp đó để lấy package thay vì xem tên package như một định danh toàn cục đủ để tìm mọi thông tin. Xem thêm [Class.getPackage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPackage()).

## Khi nào đọc ở cấp package và khi nào đọc ở cấp lớp?

| Nhu cầu | Nơi khai báo và nơi đọc |
| --- | --- |
| Tài liệu chung về vai trò của package | Javadoc trong `package-info.java` |
| Siêu dữ liệu chung của package | Annotation trên khai báo package; đọc qua `Package` |
| Cấu hình riêng cho một lớp | Annotation trên lớp; đọc qua `Class` nếu dùng reflection |
| Quy tắc áp dụng mặc định từ package cho các lớp | Cần công cụ quy định và thực hiện cách áp dụng |
| Quy tắc riêng của một package con | `package-info.java` của chính package con |

Không dùng package annotation để thay cho cơ chế `exports` hoặc `opens` của Java modules. Chúng phục vụ các mục đích khác nhau: siêu dữ liệu mô tả package và quyền truy cập do hệ module kiểm soát.

Không đặt logic nghiệp vụ hoặc danh sách khởi tạo đối tượng vào `package-info.java`. Phần xử lý nên nằm trong lớp hoặc công cụ sử dụng annotation.

## Lỗi phổ biến và cách chẩn đoán

### Annotation không được chấp nhận khi biên dịch

Kiểm tra lần lượt:

1. Kiểu annotation có cho phép `ElementType.PACKAGE` không?
2. Annotation có đứng trước khai báo `package` không?
3. Tên package có đúng với package cần mô tả không?
4. Kiểu annotation có khả năng truy cập phù hợp và được import đúng không?
5. Có khai báo annotation của cùng package bị lặp trong các tệp nguồn khác không?

Không chuyển annotation sang lớp chỉ để làm lỗi biến mất nếu mục tiêu thực sự là mô tả package. Việc đó đổi phần tử được gắn annotation.

### getAnnotation trả null

Kiểm tra:

1. Đang gọi trên `Package` hay trên `Class`?
2. Đã dùng `RetentionPolicy.RUNTIME` chưa?
3. Đã biên dịch tệp `package-info.java` chưa?
4. `package-info.class` có trong đầu ra và trong JAR đang chạy không?
5. Lớp dùng làm mốc có thực sự thuộc package đó không?
6. Ứng dụng có đang chạy đúng phiên bản đầu ra và đúng ngữ cảnh nạp lớp không?

Thư mục nguồn có tên gần giống nhau không đảm bảo các lớp thuộc cùng package. Hãy đối chiếu `package` trong mã nguồn và tên trả về từ `getPackage().getName()`.

### Trông chờ hiệu lực trên mọi package con

Nếu công cụ không có quy tắc mở rộng riêng, hãy đọc annotation trên từng package cụ thể. Muốn áp dụng cho `learn.model.order`, tạo tệp `src/learn/model/order/package-info.java` với khai báo `package learn.model.order;` và annotation phù hợp.

Đừng dùng quan hệ chuỗi “tên bắt đầu bằng `learn.model`” thay thế cho việc hiểu phạm vi áp dụng. Nếu công cụ chủ động dùng quy tắc tiền tố, cần xác định rõ ranh giới tên package và thứ tự ưu tiên của cấu hình.

## Thực hành kiểm chứng

1. Chạy ví dụ ban đầu để đối chiếu đủ sáu dòng output.
2. Đổi `owner = "training"` thành một giá trị khác, biên dịch lại rồi xác nhận chỉ giá trị đọc tương ứng thay đổi.
3. Đổi retention thành `CLASS`, biên dịch lại và giải thích vì sao package vẫn tồn tại nhưng không đọc được annotation bằng reflection.
4. Khôi phục `RUNTIME`, tạo `package-info.java` riêng cho `learn.model.order`. Gắn cùng kiểu annotation với giá trị riêng rồi xác nhận `subpackage.policy` thành `true`.
5. Đóng gói thành JAR, chạy lại từ JAR và kiểm tra kết quả khớp với chạy từ thư mục biên dịch.

Sau bài này, cần chỉ ra được **annotation gắn vào phần tử nào, được lưu đến giai đoạn nào, thành phần nào đọc nó và phạm vi nào thực sự chịu tác động**.
