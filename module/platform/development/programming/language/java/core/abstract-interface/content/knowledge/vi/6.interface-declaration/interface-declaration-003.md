# Interface cấp cao nhất: public và package-private

## 1. Vị trí khai báo và hai mức truy cập

**Top-level interface** được khai báo trực tiếp trong tệp nguồn, bên ngoài mọi class, interface, enum hoặc record khác. Một top-level interface chỉ có hai lựa chọn về mức truy cập:

| Cú pháp | Mức truy cập | Ai có thể tham chiếu tên kiểu? |
| --- | --- | --- |
| `public interface PublicService { ... }` | public | Mã ở package khác có thể dùng kiểu nếu package/module chứa nó được truy cập. |
| `interface InternalService { ... }` | package-private | Mã có quyền truy cập trong cùng package. |

Package-private không phải từ khóa. Nó được tạo bằng cách bỏ modifier truy cập. Một top-level interface không thể là `private` hoặc `protected`; `static` cũng không phải modifier hợp lệ cho top-level interface.

## 2. Tên tệp và ranh giới package

Với cách tổ chức nguồn Java thông thường, nếu một tệp có top-level type `public` thì tên tệp phải khớp tên kiểu public đó. Một tệp không nên khai báo nhiều top-level public type.

Ví dụ, tệp `PublicService.java`:

```java
package demo.api;

public interface PublicService {
    String greet(String name);
}
```

Tệp `InternalService.java` trong cùng package:

```java
package demo.api;

interface InternalService {
    String auditTag();
}
```

`InternalService` có thể được dùng từ các tệp khác trong `demo.api`, dù các tệp nằm riêng. Nó không thể được import trực tiếp từ `demo.client`. Package `demo.api.internal` cũng là package khác; tên trông giống package cha không cấp quyền package-private.

Một lớp triển khai có thể được giữ package-private và được cung cấp ra ngoài qua factory public:

```java
package demo.api;

public final class Services {
    private Services() {}

    public static PublicService create() {
        return new DefaultService();
    }
}

final class DefaultService implements PublicService, InternalService {
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }

    @Override
    public String auditTag() {
        return "internal";
    }
}
```

Mã bên ngoài package chỉ cần `PublicService service = Services.create()`. Nó không phải biết tên lớp triển khai `DefaultService`.

## 3. Quyền truy cập của kiểu khác với thành viên

Không nên suy ra rằng phương thức trong interface package-private cũng trở thành package-private. Quy tắc modifier của kiểu và thành viên là hai vấn đề riêng. Ví dụ, một phương thức abstract thông thường trong interface vẫn ngầm định `public abstract`; field interface ngầm định `public static final`.

Dù thành viên được khai báo public, mã ngoài package vẫn không thể đặt tên một kiểu top-level package-private trong khai báo của mình. Kiểu phải truy cập được trước khi quyền truy cập thành viên có ý nghĩa.

Interface được khai báo bên trong class/interface là member interface, không phải top-level interface. Member interface có quy tắc truy cập của kiểu thành viên và có thể dùng `private` hoặc `protected` khi vị trí khai báo cho phép.

## 4. Java Platform Module System (JPMS)

Trong dự án có named modules, modifier `public` là điều kiện cần nhưng chưa đủ để module khác dùng kiểu. Thường cần cả:

1. Module sử dụng đọc được module cung cấp, thông qua `requires`.
2. Module cung cấp export package chứa kiểu qua `exports`.
3. Bản thân top-level interface được khai báo `public`.

Ví dụ:

```java
module demo.api.module {
    exports demo.api;
}
```

Module khác còn phải khai báo `requires demo.api.module;`. Nếu package không được export, một public interface trong package đó không tự động trở thành API công khai cho module khác.

## 5. Checklist khi chẩn đoán lỗi truy cập

- Kiểm tra dòng `package` thực tế ở cả hai tệp; đừng dựa vào tên thư mục.
- Kiểm tra kiểu top-level có `public` nếu cần được dùng từ package khác.
- Kiểm tra tên tệp trùng với kiểu top-level public.
- Nếu có `module-info.java`, kiểm tra cả `requires` và `exports`.
- Nếu chỉ cần lớp nội bộ phối hợp, cân nhắc package-private để tránh công bố một phần API không cần thiết.

**Tự kiểm tra:** Nếu `InternalService` nằm trong `demo.api`, lớp thuộc `demo.api.client` có thể truy cập nó chỉ vì package đó có tiền tố giống nhau không? Không; đó là package khác.