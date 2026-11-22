# Readability edge và accessible package

Trong Java Platform Module System (JPMS), một module có thể phụ thuộc vào module khác nhưng điều đó chưa đủ để mọi package của module được phụ thuộc đều có thể truy cập. Khi phân tích module graph, cần tách hai khái niệm:

- **Readability edge:** quan hệ cho biết module nào có thể đọc các kiểu được cung cấp bởi module nào. Quan hệ này được hình thành chủ yếu từ directive `requires`.
- **Accessible package:** package mà module gọi được phép truy cập qua ranh giới module. Module chứa package phải export package đó cho module gọi, đồng thời kiểu và thành viên vẫn phải đáp ứng access modifier Java.

Một lời gọi API giữa hai named module chỉ hợp lệ khi module gọi đọc được module cung cấp, package chứa API được export cho module gọi và kiểu/thành viên có mức truy cập phù hợp. Readability và package accessibility là hai điều kiện riêng, cần kiểm tra cả hai khi xử lý lỗi module.

## 1. Readability edge trong module graph

Module graph mô tả các module đã được phân giải và các quan hệ phụ thuộc giữa chúng. Khi module `com.acme.app` khai báo:

```java
module com.acme.app {
    requires com.acme.library;
}
```

JPMS tạo quan hệ readability từ `com.acme.app` tới `com.acme.library`. Có thể hình dung cạnh trong graph:

```text
com.acme.app  ──requires──>  com.acme.library
```

Điều đó cho phép mã trong `com.acme.app` tham chiếu các kiểu thuộc module `com.acme.library`, nếu package của những kiểu đó được export phù hợp. `requires` không làm mọi package của thư viện trở thành API công khai.

Module graph được xây dựng khi compiler hoặc runtime phân giải module. Nếu một dependency bắt buộc không có trên module path hoặc không thể phân giải, quá trình biên dịch hoặc khởi chạy sẽ thất bại trước khi ứng dụng sử dụng API.

## 2. Readability không đồng nghĩa với accessibility

Giả sử module thư viện có class public:

```java
package com.acme.internal;

public class InternalClient {
    public void connect() {
        System.out.println("Connected");
    }
}
```

Descriptor của thư viện:

```java
module com.acme.library {
}
```

Descriptor của ứng dụng:

```java
module com.acme.app {
    requires com.acme.library;
}
```

Ứng dụng đã đọc được module thư viện vì có cạnh `requires`. Tuy nhiên, package `com.acme.internal` không được export. Do đó, ứng dụng không thể import `InternalClient`, mặc dù class và method đều là `public`.

Có thể kiểm tra theo hai câu hỏi độc lập:

1. **Readability:** module gọi có đọc được module chứa class không?
2. **Package accessibility:** module chứa class có export package đó cho module gọi không?

Nếu readability thiếu, hãy kiểm tra `requires` và module resolution. Nếu readability đã có nhưng package vẫn không truy cập được, hãy kiểm tra `exports`, qualified export và access modifier.

## 3. Điều kiện để package trở nên accessible

Đối với một named module khác muốn dùng API, cần thỏa mãn các điều kiện chính:

1. Module chứa package đã được phân giải trong module graph.
2. Module gọi đọc được module chứa package.
3. Package được export không điều kiện hoặc export có điều kiện cho đúng module gọi.
4. Kiểu được truy cập là public; constructor và member được gọi cũng phải có visibility phù hợp.
5. Các kiểu xuất hiện trong chữ ký API cũng phải có thể truy cập theo quy tắc tương ứng.

Ví dụ, descriptor thư viện:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Descriptor ứng dụng:

```java
module com.acme.app {
    requires com.acme.library;
}
```

Nếu `com.acme.api.Client` là public, ứng dụng có thể import và sử dụng nó. Package khác như `com.acme.library.internal` vẫn bị đóng nếu không export.

Điều kiện accessibility được xác định ở cấp package. Directive `exports` không thể chỉ export một class riêng lẻ trong package; nếu package được export, các kiểu public trong package có thể trở thành một phần API.

## 4. Unqualified export và qualified export

Unqualified export cho phép mọi module đọc được module cung cấp truy cập package:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Qualified export chỉ cho phép những module được chỉ định:

```java
module com.acme.library {
    exports com.acme.spi to com.acme.app, com.acme.testkit;
}
```

Nếu `com.acme.other` khai báo `requires com.acme.library;` nhưng không nằm trong danh sách đích, module đó vẫn không truy cập được `com.acme.spi`. Readability edge tồn tại nhưng package không accessible cho module đó.

Điều này hữu ích khi thư viện có API nội bộ dành riêng cho một số module hợp tác, chẳng hạn ứng dụng chính hoặc test kit. Với API công khai cho nhiều consumer, unqualified export thường phù hợp hơn.

## 5. Readability được mở rộng bởi requires transitive

Một module có thể cần expose dependency của nó cho các module downstream. Directive `requires transitive` tạo quan hệ readability bắc cầu.

Giả sử graph có ba module:

```text
com.acme.app  ──requires──>  com.acme.facade
                                  |
                                  └──requires transitive──> com.acme.api
```

Descriptor của facade:

```java
module com.acme.facade {
    requires transitive com.acme.api;
    exports com.acme.facade;
}
```

Descriptor của ứng dụng:

```java
module com.acme.app {
    requires com.acme.facade;
}
```

Do `com.acme.facade` khai báo `requires transitive com.acme.api`, module đọc được facade cũng đọc được `com.acme.api`. Vì vậy, mã ứng dụng có thể sử dụng các kiểu API trong dependency đó khi package tương ứng được export.

`requires transitive` không tự export package của module facade và cũng không tự export package của dependency. Nó chỉ mở rộng readability. Package accessibility vẫn do module sở hữu package quyết định.

Dùng `requires transitive` khi dependency xuất hiện trong public API của module, ví dụ kiểu trả về hoặc tham số của API công khai thuộc module dependency. Không dùng nó chỉ để làm cho graph rộng hơn; mỗi cạnh bắc cầu làm tăng dependency mà downstream phải nhìn thấy.

## 6. requires static và readability theo môi trường

`requires static` khai báo dependency cần có khi biên dịch nhưng có thể không cần hiện diện trong runtime image:

```java
module com.acme.tooling {
    requires static com.acme.annotations;
}
```

Cách này thường dùng cho annotation hoặc công cụ hỗ trợ chỉ cần trong quá trình biên dịch. Module phải có dependency đó khi biên dịch, còn khi chạy dependency có thể không được đưa vào runtime configuration.

Nếu module được yêu cầu thực sự hiện diện trong runtime configuration, quan hệ readability được áp dụng theo module graph runtime. Vì vậy, khi phân tích lỗi, cần phân biệt graph tại compile time và graph tại runtime. Không nên mặc định mọi dependency `requires static` luôn có mặt khi chạy.

Có thể kết hợp hai modifier:

```java
module com.acme.tooling {
    requires static transitive com.acme.annotations;
}
```

Tổ hợp này làm dependency có tính bắc cầu ở compile time, nhưng vẫn optional ở runtime. Chỉ dùng khi hợp đồng API và cách phân phối thật sự cần hành vi đó.

## 7. java.base và các quan hệ readability mặc định

Mọi named module thông thường đều đọc được `java.base`. Nếu source descriptor không viết `requires java.base;`, compiler bổ sung dependency bắt buộc này vào module descriptor đã biên dịch.

Ví dụ:

```java
module com.acme.app {
}
```

Module vẫn sử dụng được `String`, `Object`, `List` và nhiều API cốt lõi vì các API này thuộc `java.base`. Đây là dependency nền tảng được JPMS quy định.

Tuy nhiên, không phải mọi module JDK đều tự động readable. Nếu ứng dụng dùng JDBC, logging hoặc HTTP Client, cần khai báo dependency tương ứng, chẳng hạn:

```java
module com.acme.reporting {
    requires java.sql;
    requires java.logging;
}
```

Readability tới `java.base` không tự tạo readability tới `java.sql` hay `java.logging`.

## 8. Accessible package khác deep reflection

`exports` cho phép truy cập kiểu public theo quy tắc Java thông thường. Nó không tự cấp quyền truy cập sâu vào field hoặc method private bằng reflection.

Nếu framework cần deep reflection, package phải được mở:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
```

Trong ví dụ này, consumer có thể dùng public API thuộc `com.acme.domain.api`; module ORM có thể reflection sâu vào package entity. `opens` không thay thế `exports` khi mã Java cần import kiểu public ở thời điểm biên dịch.

Có thể kiểm tra hai trạng thái bằng API runtime:

```java
Module source = Client.class.getModule();
Module caller = Main.class.getModule();

boolean exported = source.isExported("com.acme.api", caller);
boolean opened = source.isOpen("com.acme.entity", caller);

System.out.println("Exported: " + exported);
System.out.println("Opened: " + opened);
```

Hai phép kiểm tra trả lời hai câu hỏi khác nhau. Nếu API thông thường không truy cập được, xem `isExported`; nếu deep reflection bị từ chối, xem `isOpen`.

## 9. Ví dụ graph có readability nhưng thiếu accessible package

Giả sử module graph có:

```text
com.acme.app  ──requires──>  com.acme.library
```

Descriptor thư viện:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Thư viện có hai class:

```java
package com.acme.api;

public class PublicClient {
}
```

```java
package com.acme.internal;

public class InternalClient {
}
```

Ứng dụng có thể import `com.acme.api.PublicClient`, nhưng không thể import `com.acme.internal.InternalClient`. Cả hai class đều public, module app đọc được module library, nhưng chỉ package `com.acme.api` được export.

Nếu đổi descriptor thư viện thành:

```java
module com.acme.library {
    exports com.acme.api;
    exports com.acme.internal to com.acme.app;
}
```

thì package internal cũng trở nên accessible với `com.acme.app`, nhưng không được công khai cho các module khác. Ví dụ này cho thấy module graph chỉ mô tả readability; muốn biết module gọi có thể dùng một package cụ thể hay không, phải xem export target của package.

## 10. Công cụ chẩn đoán module graph và package

Có thể xem descriptor của JAR:

```shell
jar --describe-module --file library.jar
```

Để xem quá trình phân giải module khi chạy:

```shell
java --show-module-resolution \
    --module-path mods \
    --module com.acme.app/com.acme.app.Main
```

Công cụ `jdeps` hỗ trợ kiểm tra dependency và module:

```shell
jdeps --module-path mods --check com.acme.app
```

Khi xử lý lỗi truy cập, hãy đọc kết quả theo thứ tự:

- Module chứa package có thực sự nằm trong module graph không?
- Module gọi có readability edge tới module cung cấp không?
- Package được export không, và nếu là qualified export thì module gọi có nằm trong danh sách không?
- Kiểu và member được gọi có visibility phù hợp không?
- Framework có cần deep reflection và package đã được mở cho đúng module chưa?

Nếu module không được phân giải, xử lý module path hoặc dependency trước. Nếu module đã readable nhưng package không accessible, sửa `exports` phù hợp. Nếu chỉ deep reflection thất bại, kiểm tra `opens` thay vì mở rộng API công khai.

## 11. Nguyên tắc thiết kế

- Dùng `requires` để khai báo dependency và tạo readability edge.
- Dùng `exports` để công bố package chứa API public.
- Dùng qualified export khi package chỉ dành cho một số module đã xác định.
- Giữ package triển khai không export để tránh biến chi tiết nội bộ thành hợp đồng công khai.
- Dùng `requires transitive` khi dependency là một phần của public API downstream.
- Dùng `requires static` cho dependency cần ở compile time nhưng có thể optional ở runtime.
- Dùng `opens` riêng cho nhu cầu deep reflection; không nhầm nó với API accessibility.
- Kiểm tra module descriptor và graph thực tế khi lỗi chỉ xuất hiện trên module path.

Readability trả lời câu hỏi module nào có thể đọc module nào. Package accessibility trả lời câu hỏi module gọi có được phép sử dụng package cụ thể hay không. Phân biệt hai khái niệm này giúp đọc module graph chính xác và xử lý lỗi truy cập ở đúng lớp của JPMS.