# Đặt tên, tổ chức package và chọn phạm vi truy cập cho annotation type trong Java

## 1. Annotation type cũng là một kiểu Java

Trong Java, một annotation tự định nghĩa được khai báo bằng cú pháp `@interface`. Khai báo đó tạo ra **annotation type** có tên đầy đủ (fully qualified name), package, quy tắc truy cập và khả năng được sử dụng từ các lớp khác. Vì vậy, thiết kế annotation type cần quan tâm đến ba câu hỏi: đặt tên sao cho diễn đạt đúng ý nghĩa, đặt nó ở package nào và cho những nguồn mã nào được phép tham chiếu đến tên đó.

Ví dụ một annotation type rất nhỏ:

```java
package com.example.order.annotations;

public @interface Reviewed {
}
```

Ở đây:

- `Reviewed` là **simple name**, được dùng dưới dạng `@Reviewed` sau khi import hoặc khi ở cùng package.
- `com.example.order.annotations.Reviewed` là **fully qualified name** (tên đủ điều kiện) để phân biệt với các kiểu `Reviewed` ở package khác.
- `public` quyết định khả năng truy cập tên annotation type từ nơi khác, vẫn chịu các giới hạn của module nếu ứng dụng dùng Java Platform Module System (JPMS).
- `@interface` là cú pháp khai báo một annotation type; tên sau `@interface` tuân theo quy tắc định danh Java, giống tên class/interface.

**Phân biệt hai vấn đề:** visibility của *kiểu annotation* quyết định mã nguồn ở đâu có thể dùng `@Reviewed`; còn `@Target` và `@Retention` quyết định annotation có thể được gắn vào thành phần nào và được lưu giữ đến giai đoạn nào. `@Target`/`@Retention` không thay thế access modifier.

## 2. Đặt tên: đọc lên biết annotation biểu đạt điều gì

Tên annotation là một phần của API vì xuất hiện trực tiếp trước các khai báo. Nên ưu tiên tên **ngắn, rõ, mang ý nghĩa nghiệp vụ hoặc hành vi được công cụ xử lý**, dùng **UpperCamelCase** (PascalCase), ví dụ:

| Tên | Ý nghĩa dự kiến | Nhận xét |
| --- | --- | --- |
| `@Reviewed` | Thành phần đã qua bước review theo quy ước dự án | Diễn tả một trạng thái |
| `@RequiresApproval` | Thành phần cần kiểm tra phê duyệt | Diễn tả một yêu cầu |
| `@Audited` | Thành phần được đánh dấu để hệ thống audit xử lý | Có ý nghĩa nếu thật sự có bộ xử lý audit |
| `@InternalApi` | API dành cho việc dùng nội bộ | Nêu giới hạn sử dụng về mặt hợp đồng |
| `@A1`, `@Flag2`, `@MyAnnotation` | Ý nghĩa khó đoán | Nên tránh nếu không có ngữ cảnh đặc biệt |

Quy tắc đặt tên hữu ích:

1. **Tên biểu đạt hợp đồng**, không chỉ mô tả một kỹ thuật. Ví dụ `@RequiresApproval` nói rõ nghĩa hơn `@CheckFlag`.
2. **Giữ nhất quán trong cùng module.** Nếu nhóm tên mô tả trạng thái bằng tính từ, đừng tùy tiện đảo sang cách đặt tên mơ hồ ở những annotation liên quan.
3. **Không cần thêm hậu tố `Annotation` vào mọi tên.** `@Reviewed` thường gọn hơn `@ReviewedAnnotation`. Dùng hậu tố nếu nó thực sự giúp phân biệt tên.
4. **Không đặt trùng tên dễ gây nhầm với annotation chuẩn**, như `Override`, `Deprecated` hay `SuppressWarnings`. Nếu có hai kiểu cùng simple name, phải phân biệt bằng import hoặc fully qualified name.
5. **Chọn tên ổn định** cho annotation được publish như thư viện: đổi package hoặc tên type buộc các nơi sử dụng phải sửa import/chỗ gắn annotation.

Tên có ý nghĩa vẫn không tự tạo hành vi. Ví dụ gắn `@Audited` lên method **không làm Java tự ghi nhật ký**. Phải có compiler, annotation processor, framework hoặc mã reflection phù hợp để đọc và hành động trên annotation.

## 3. Tổ chức package: đặt annotation theo phạm vi sở hữu và cách sử dụng

Java sử dụng package để tạo không gian tên và nhóm những kiểu liên quan. Với annotation type, nên đặt nó gần **hợp đồng hoặc tính năng mà nó phục vụ**, đặc biệt khi annotation là một phần API được nhiều package sử dụng.

Một ví dụ cấu trúc:

```text
src/
└── com/
    └── example/
        └── order/
            ├── annotations/
            │   ├── Reviewed.java
            │   └── RequiresApproval.java
            ├── internal/
            │   └── InternalOnly.java
            └── service/
                └── OrderService.java
```

- Các annotation được code bên ngoài dùng thường xuyên có thể đặt trong `com.example.order.annotations` (hoặc `annotation`; chọn một quy ước thống nhất).
- Annotation chỉ phục vụ cài đặt một phần tính năng có thể nằm ngay trong package tính năng ấy hoặc một package `internal` thích hợp.
- Với dự án lớn, phân chia theo domain hoặc module, ví dụ `com.example.payment.annotations` và `com.example.inventory.annotations`, giúp mỗi phần sở hữu hợp đồng của mình.

Các quy ước Java nên tuân thủ:

- Tên package thường viết **chữ thường**, ví dụ `com.example.order.annotations`, giúp tránh nhầm với tên class và hạn chế lỗi khác biệt chữ hoa/chữ thường giữa hệ thống tệp.
- Ưu tiên tên miền đảo ngược để giảm xung đột không gian tên. Tránh tự tạo package trong namespace dành cho nền tảng như `java.*`.
- Trong tệp nguồn nên khai báo `package` ở đầu tệp (sau chú thích và các annotation dành cho package nếu có), rồi đến `import` và khai báo type.
- Theo cấu trúc dự án Java thông dụng, `package com.example.order.annotations;` tương ứng thư mục `com/example/order/annotations`. Khi truyền tệp trực tiếp cho `javac`, vị trí tệp nguồn không nhất thiết phải như vậy về mặt cú pháp, nhưng cấu trúc khớp package giúp IDE/build tool và người đọc làm việc đúng.
- Tránh đưa toàn bộ annotation không liên quan vào một package tiện ích chung, khiến ranh giới domain khó thấy và làm phát sinh phụ thuộc không cần thiết.
- Tránh **default package** cho code tái sử dụng: các type nằm trong unnamed package không thể được import từ named package.

Nếu một annotation dành để đánh dấu *package*, định nghĩa nó với `@Target(ElementType.PACKAGE)` và gắn trên khai báo `package` trong **`package-info.java`**. Đây là tình huống khác với annotation được đặt trên class hoặc method; cùng một nguyên tắc về tên và quyền truy cập vẫn áp dụng.

## 4. Chọn phạm vi truy cập cho annotation type

### 4.1. Annotation type top-level: public hoặc package-private

Ở mức **top-level** (khai báo trực tiếp trong tệp, không lồng trong class/interface), hai lựa chọn thông dụng và hợp lệ là:

| Cách khai báo | Ai có thể tham chiếu trực tiếp kiểu annotation? | Khi nào dùng? |
| --- | --- | --- |
| `public @interface Reviewed {}` | Các package khác có thể dùng khi package/type được truy cập hợp lệ | Annotation thuộc API chung hoặc hợp đồng được nhiều package dùng |
| `@interface InternalMarker {}` | Mã nguồn trong **cùng package** | Annotation chỉ cần dùng nội bộ package |

Không được khai báo `private @interface` hoặc `protected @interface` ở top-level. `private`/`protected` có ý nghĩa đối với **member type lồng bên trong một class** theo quy tắc của class đó.

Với một `public` annotation type top-level có tên `Reviewed`, tệp mã nguồn phải có tên **`Reviewed.java`** theo quy tắc tên tệp của Java khi biên dịch nguồn thông thường. Một tệp nguồn không thể chứa hai public top-level type có tên khác nhau để đóng vai trò các khai báo public độc lập như vậy.

### 4.2. Annotation type được khai báo lồng

Bạn có thể khai báo annotation type bên trong một class như một member type:

```java
class Workflow {
    private @interface LocalMarker {}

    @LocalMarker
    void step() {}
}
```

`LocalMarker` được giấu trong phạm vi truy cập phù hợp với `private` member type của `Workflow`. Ví dụ này chỉ minh họa cú pháp hợp lệ; nó không có `main` để chạy độc lập. Member annotation type về bản chất là static như các member interface type; không gắn với một thể hiện `Workflow`.

Một annotation type khai báo bên trong **interface** là member type công khai theo quy tắc của interface, không thể dùng `private` theo cách thành viên class ở ví dụ trên. Đừng sử dụng nested annotation chỉ để che một API đáng lẽ cần được tái sử dụng rõ ràng từ package riêng.

### 4.3. Thành phần *bên trong* annotation type

Các phần tử của annotation được khai báo dưới dạng method không có tham số, ví dụ:

```java
public @interface Reviewed {
    String reviewer() default "team";
}
```

`reviewer()` là một **annotation element**: phương thức này mặc định mang đặc tính `public abstract`. Điều đó **không có nghĩa annotation type chứa nó tự động public**. Quyền truy cập của chính `@interface Reviewed` vẫn do modifier ở khai báo type quyết định.

Annotation element có hạn chế riêng về kiểu dữ liệu và giá trị mặc định. Khi thiết kế một annotation chung, không nên nhầm các ràng buộc đó với visibility của type.

## 5. Ví dụ Java 17+ chạy được: public và package-private trên nhiều package

Ta tạo một annotation public dùng xuyên package và một annotation package-private chỉ dùng nội bộ. Trong ví dụ, `Reviewed` được giữ lại đến runtime để `Main` đọc bằng reflection; `InternalMarker` chỉ dùng trong cùng package và giữ lại ở source. Những lựa chọn `RetentionPolicy` phục vụ minh họa mục đích sử dụng; chúng **không mở hay đóng phạm vi truy cập**.

Cấu trúc đầy đủ của năm dòng chức năng được tổ chức thành bốn tệp nguồn:

```text
src/
└── com/example/training/annotation/
    ├── api/
    │   └── Reviewed.java
    ├── impl/
    │   ├── InternalMarker.java
    │   └── ReportService.java
    └── app/
        └── Main.java
```

**Tệp 1: `src/com/example/training/annotation/api/Reviewed.java`**

```java
package com.example.training.annotation.api;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Reviewed {
    String reviewer() default "team";
}
```

`public` cho phép package `impl` và `app` tham chiếu đến annotation. `@Target` chỉ cho phép gắn lên khai báo type hoặc method; `@Retention(RUNTIME)` giúp có thể quan sát bằng reflection lúc chạy. `@Documented` khiến annotation xuất hiện trong tài liệu Javadoc của thành phần được chú thích khi phù hợp; nó không làm annotation tự xử lý nghiệp vụ.

**Tệp 2: `src/com/example/training/annotation/impl/InternalMarker.java`**

```java
package com.example.training.annotation.impl;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface InternalMarker {
}
```

Do không có modifier `public`, `InternalMarker` là **package-private**. Mã ở `impl` có thể sử dụng nó, nhưng `Main` ở `app` không thể import/trực tiếp tham chiếu `InternalMarker`. `SOURCE` nghĩa là marker này không được giữ trong class file để truy xuất qua reflection.

**Tệp 3: `src/com/example/training/annotation/impl/ReportService.java`**

```java
package com.example.training.annotation.impl;

import com.example.training.annotation.api.Reviewed;

@InternalMarker
@Reviewed(reviewer = "qa")
public class ReportService {
    @Reviewed(reviewer = "dev")
    public String status() {
        return "ready";
    }
}
```

`ReportService` có thể dùng `@InternalMarker` vì khai báo của cả hai ở cùng package `impl`, dù chúng nằm trong hai tệp khác nhau. `ReportService` cũng dùng được `@Reviewed` nhờ annotation type công khai và import đúng.

**Tệp 4: `src/com/example/training/annotation/app/Main.java`**

```java
package com.example.training.annotation.app;

import com.example.training.annotation.api.Reviewed;
import com.example.training.annotation.impl.ReportService;

public class Main {
    public static void main(String[] args) throws NoSuchMethodException {
        Reviewed typeInfo = ReportService.class.getAnnotation(Reviewed.class);
        Reviewed methodInfo = ReportService.class
                .getDeclaredMethod("status")
                .getAnnotation(Reviewed.class);

        System.out.println(typeInfo.reviewer());
        System.out.println(methodInfo.reviewer());
        System.out.println(new ReportService().status());
    }
}
```

Đứng ở thư mục chứa `src`, dùng JDK 17 trở lên để biên dịch; lệnh được viết trên một dòng để dùng với shell thông thường:

```bash
javac --release 17 -d out src/com/example/training/annotation/api/Reviewed.java src/com/example/training/annotation/impl/InternalMarker.java src/com/example/training/annotation/impl/ReportService.java src/com/example/training/annotation/app/Main.java
java -cp out com.example.training.annotation.app.Main
```

**Stdout chính xác:**

```text
qa
dev
ready
```

Giải thích kết quả:

1. `javac -d out` đặt các `.class` vào cây thư mục package bên dưới `out`.
2. `Main` truy cập được `ReportService` và `Reviewed` vì chúng là public top-level types, trong ví dụ classpath không có thêm hạn chế module.
3. Reflection tìm được `@Reviewed` trên class và method vì annotation có `RetentionPolicy.RUNTIME`.
4. Cú pháp `reviewer = "qa"` và `reviewer = "dev"` đặt giá trị riêng cho annotation element; đây là dữ liệu metadata, không khiến `status()` tự làm thêm công việc gì.
5. `InternalMarker` chỉ được dùng trong `impl`, đúng với visibility package-private của nó.

Thử viết `import com.example.training.annotation.impl.InternalMarker;` trong `Main.java` sẽ gây lỗi biên dịch về quyền truy cập: một top-level type không public không thể truy cập từ bên ngoài package của nó.

## 6. Những nhầm lẫn dễ gặp

### 6.1. Nghĩ @Retention(RUNTIME) đồng nghĩa public

Sai. `@Retention(RetentionPolicy.RUNTIME)` chỉ quy định annotation còn tồn tại để runtime có thể quan sát bằng cơ chế hỗ trợ. Nó không mở quyền import từ package khác. Ngược lại, một annotation `public` nhưng dùng `SOURCE` vẫn import và dùng trong code bên ngoài package khi biên dịch bình thường, chỉ không còn trong bytecode.

### 6.2. Nghĩ @Target quyết định package có được dùng hay không

`@Target(ElementType.TYPE)` có nghĩa annotation có thể được gắn vào khai báo type phù hợp; `ElementType.METHOD` cho method; `ElementType.PACKAGE` cho khai báo package. `@Target` không phải access control. Muốn giới hạn nơi có thể **tham chiếu annotation type theo visibility ngôn ngữ**, dùng phạm vi truy cập và thiết kế package thích hợp.

### 6.3. Chọn package-private dù API cần dùng nhiều package

Nếu nhiều service ở các package khác nhau cần dùng `@Reviewed`, hãy đặt annotation ở package API hợp lý và cho nó `public`. Đừng rải bản sao cùng tên ở từng package; việc đó tạo ra các kiểu annotation khác nhau, khó phát hiện bằng tool/framework đọc metadata.

### 6.4. Đưa tất cả annotation vào gói chung

Package `com.example.annotations` không hẳn sai, nhưng nếu chứa annotation từ nhiều domain không liên quan sẽ làm giảm khả năng định vị, tăng phụ thuộc và khiến quyền sở hữu API mơ hồ. Dùng package có chủ đích như `com.example.order.annotations` khi phạm vi domain là rõ ràng.

### 6.5. Nhầm public của type với khả năng truy cập trong JPMS

Trong một dự án **không dùng JPMS** và cùng classpath, `public` top-level type cho phép package khác tham chiếu khi phụ thuộc có mặt. Trong **named module**, module sử dụng còn phải có quan hệ đọc module cung cấp (ví dụ `requires`), và package chứa type công khai phải được `exports` phù hợp để truy cập thông thường từ module khác. `opens` phục vụ truy cập phản chiếu sâu theo quy tắc JPMS, không thay cho `exports` để biên dịch import API thông thường.

### 6.6. Đổi tên annotation mà quên nơi tiêu thụ

Ví dụ đổi `@Reviewed` thành `@ReviewChecked` cần xem cả nơi sử dụng trong mã Java và nơi các công cụ đọc annotation. Đặc biệt với annotation library công khai, tên đủ điều kiện là một phần hợp đồng. Nếu một framework tìm kiểu cũ trong metadata, việc chỉ sửa import của một vài class là chưa đủ.

## 7. Quy trình thiết kế annotation type

Khi thêm một annotation mới vào codebase:

1. **Xác định người tiêu thụ:** compiler/annotation processor, framework, reflection, công cụ sinh tài liệu hay chỉ là marker về quy ước.
2. **Đặt tên theo ý nghĩa:** một developer đọc `@TênAnnotation` nên hiểu annotation đánh dấu điều gì.
3. **Chọn package theo phạm vi sở hữu:** annotation chia sẻ ở package API; marker chỉ phục vụ nội bộ đặt gần phần triển khai.
4. **Chọn visibility:** `public` khi cần được tham chiếu từ các package khác; package-private khi giới hạn dùng trực tiếp trong cùng package; nested private/protected chỉ khi phạm vi lồng thực sự phù hợp.
5. **Chọn `@Target`, `@Retention` theo cách dùng thực tế:** phải có `RUNTIME` nếu cần đọc qua reflection lúc chạy; `SOURCE` có thể đủ cho annotation processor chạy lúc biên dịch; `CLASS` giữ trong class file mà không bắt buộc có sẵn cho runtime reflection.
6. **Kiểm tra ở một caller thuộc package khác:** biên dịch ví dụ sử dụng annotation, xác nhận import, quyền truy cập, package path và dữ liệu runtime nếu có.
7. **Giữ tên/package ổn định** nếu annotation là một phần API công khai; khi cần đổi, quản lý việc cập nhật consumer như một thay đổi hợp đồng.

**Ghi nhớ:** `@interface` tạo một **kiểu Java**. Tên có ý nghĩa giúp code dễ đọc, package xác định vị trí và quyền sở hữu, còn access modifier kiểm soát khả năng tham chiếu trực tiếp đến kiểu đó. `@Target` và `@Retention` giải quyết các khía cạnh khác của annotation nên phải được chọn độc lập với visibility.
