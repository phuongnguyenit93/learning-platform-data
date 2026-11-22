# `open module` và mở toàn bộ package

Trong Java Platform Module System (JPMS), module có thể giới hạn package nào được module khác truy cập. Tuy nhiên, một số thư viện cần framework hoặc công cụ dùng reflection để đọc thành viên không public, chẳng hạn field private, constructor hoặc phương thức được khai báo trong class. Directive `open module` cho phép mở toàn bộ package của một named module cho deep reflection ở runtime.

Cần phân biệt hai cơ chế: **exports** cho phép module khác truy cập các kiểu public của package theo quy tắc Java thông thường; **opens** cho phép reflection vượt qua kiểm tra truy cập ở runtime. Mở package không đồng nghĩa với xuất package.

## 1. Cú pháp của open module

Một module có thể khai báo:

    open module com.example.domain {
        requires java.logging;
        exports com.example.domain.api;
    }

Từ khóa `open` đứng trước `module`. Khi module được khai báo theo cách này, **tất cả package của module đều được mở cho deep reflection đối với các module khác**.

Trong module descriptor:

- Có thể khai báo các directive như `requires`, `exports`, `uses` và `provides` như bình thường.
- Không được khai báo thêm directive `opens`, vì toàn bộ package đã được mở bởi `open module`.
- Vẫn cần `exports` nếu muốn module khác truy cập kiểu public của package bằng mã Java thông thường.

`open module` chỉ áp dụng cho named module có module descriptor tường minh. Nó không làm cho các package tự động trở thành API công khai.

## 2. Deep reflection là gì?

Reflection cho phép chương trình kiểm tra class, constructor, field và method trong lúc chạy. Ví dụ, API reflection có thể lấy một field theo tên:

    Field field = type.getDeclaredField("password");

Theo quy tắc truy cập thông thường, một module không thể tùy ý dùng reflection để truy cập thành viên private nằm trong package của module khác. JPMS bảo vệ ranh giới đóng gói này ngay cả khi ứng dụng đã có class trên module path.

Deep reflection là trường hợp chương trình yêu cầu reflection bỏ qua một số kiểm tra truy cập Java thông thường, thường bằng `setAccessible(true)` hoặc `trySetAccessible()`. Việc này chỉ được cho phép khi module sở hữu package đã mở package đó cho module đang thực hiện reflection.

Với một `open module`, mọi package đều được mở, vì vậy module khác có thể yêu cầu quyền truy cập sâu vào các thành viên của class trong các package đó. `trySetAccessible()` trả về `true` khi có thể bật quyền truy cập; nếu không được phép, nó trả về `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException` khi module không mở package cần thiết.

## 3. Ví dụ: mở toàn bộ package cho reflection

Giả sử có hai module:

    src/
    ├── com.example.domain/
    │   ├── module-info.java
    │   └── com/example/domain/
    │       ├── api/SecretFactory.java
    │       └── internal/Secret.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

### Module domain

File `src/com.example.domain/module-info.java`:

    open module com.example.domain {
        exports com.example.domain.api;
    }

Module mở mọi package cho deep reflection. Riêng package `com.example.domain.api` được xuất để ứng dụng có thể gọi API public bằng mã Java thông thường.

File `src/com.example.domain/com/example/domain/api/SecretFactory.java`:

    package com.example.domain.api;

    import com.example.domain.internal.Secret;

    public final class SecretFactory {
        private SecretFactory() {
        }

        public static Object create() {
            return new Secret();
        }
    }

File `src/com.example.domain/com/example/domain/internal/Secret.java`:

    package com.example.domain.internal;

    public final class Secret {
        private final String code = "MODULE-PRIVATE";
    }

Package `com.example.domain.internal` không được export. Ứng dụng không thể import class `Secret` trực tiếp trong mã nguồn, nhưng có thể nhận đối tượng qua API public trả về kiểu `Object`.

### Module ứng dụng

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.domain;
    }

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.domain.api.SecretFactory;
    import java.lang.reflect.Field;

    public class Main {
        public static void main(String[] args) throws Exception {
            Object secret = SecretFactory.create();

            Field code = secret.getClass().getDeclaredField("code");

            if (!code.trySetAccessible()) {
                throw new IllegalStateException(
                        "Package chứa Secret chưa được mở cho reflection"
                );
            }

            System.out.println(code.get(secret));
        }
    }

Biên dịch và chạy từ thư mục chứa `src`:

    javac --module-source-path src -d out -m com.example.domain,com.example.app

    java --module-path out -m com.example.app/com.example.app.Main

Kết quả:

    MODULE-PRIVATE

Ứng dụng không import class nội bộ `Secret`. Nó chỉ nhận đối tượng qua API public, sau đó dùng reflection để tìm field `code`. Vì `com.example.domain` là open module, package `com.example.domain.internal` đã được mở cho ứng dụng; `trySetAccessible()` có thể bật quyền truy cập field private.

## 4. open module không giống exports

Hai directive phục vụ hai mục đích khác nhau:

| Khía cạnh | `exports` | `opens` / `open module` |
|---|---|---|
| Mục đích | Cho phép truy cập kiểu public của package | Cho phép deep reflection vào package |
| Thời điểm chính | Kiểm tra truy cập khi biên dịch và liên kết | Kiểm tra truy cập reflection ở runtime |
| Thành viên private | Không mở quyền truy cập private | Có thể cho phép reflection truy cập sâu |
| Tự động làm package có thể import? | Có, nếu module tiêu thụ đọc module và package được export phù hợp | Không |
| Phạm vi | Package được chỉ định | Package được chỉ định hoặc toàn bộ package của open module |

Ví dụ:

    module com.example.domain {
        exports com.example.domain.api;
    }

Directive này cho phép module đọc `com.example.domain` sử dụng các kiểu public trong package API. Nó không cho phép framework bên ngoài tự do truy cập field private trong package đó.

Ngược lại:

    module com.example.domain {
        opens com.example.domain.internal;
    }

Directive `opens` mở package nội bộ cho deep reflection ở runtime, nhưng không cho phép ứng dụng viết `import com.example.domain.internal.Secret;` để sử dụng class đó trực tiếp. Muốn truy cập theo cách thông thường, package vẫn cần được export.

## 5. Mở một package hoặc mở toàn bộ module

Không phải lúc nào cũng cần `open module`. JPMS cung cấp directive `opens` để chọn phạm vi hẹp hơn.

### Mở một package cho mọi module

    module com.example.domain {
        exports com.example.domain.api;
        opens com.example.domain.internal;
    }

Chỉ package `com.example.domain.internal` được mở cho deep reflection. Các package còn lại vẫn được bảo vệ theo module descriptor.

### Mở một package cho module cụ thể

    module com.example.domain {
        exports com.example.domain.api;
        opens com.example.domain.internal to com.example.orm;
    }

Đây là **qualified opens**. Chỉ module `com.example.orm` được mở quyền deep reflection vào package `com.example.domain.internal`. Những module khác không nhận quyền này.

### Mở toàn bộ package

    open module com.example.domain {
        exports com.example.domain.api;
    }

Đây là lựa chọn rộng nhất: mọi package của `com.example.domain` đều mở cho deep reflection. Không thể thu hẹp phạm vi bằng cách thêm `opens` vào bên trong open module.

## 6. Khi nào nên dùng open module?

`open module` có thể phù hợp khi module được thiết kế để làm việc với framework dựa nhiều vào reflection và framework cần truy cập nhiều package, ví dụ:

- Framework ánh xạ object với cơ sở dữ liệu (ORM) cần đọc field hoặc constructor.
- Bộ chuyển đổi JSON cần truy cập thuộc tính hoặc constructor theo quy tắc riêng.
- Framework dependency injection cần phân tích class và tạo instance.
- Công cụ kiểm thử hoặc serialization cần kiểm tra cấu trúc nội bộ của object.

Tuy vậy, hãy cân nhắc phạm vi truy cập. Nếu framework chỉ cần reflection trên một vài package, `opens package.name to framework.module;` thường thể hiện ý định rõ hơn và giữ được ranh giới đóng gói cho các package còn lại.

Không nên dùng `open module` chỉ để xử lý một lỗi reflection đơn lẻ khi có thể mở đúng package và đúng module tiêu thụ.

## 7. Thêm opens từ dòng lệnh

Trong một số tình huống chạy ứng dụng hoặc kiểm thử, có thể cần mở package mà không sửa `module-info.java`. JVM hỗ trợ tùy chọn:

    --add-opens source.module/package=target.module

Ví dụ:

    java --module-path out --add-opens com.example.domain/com.example.domain.internal=com.example.app -m com.example.app/com.example.app.Main

Tùy chọn này mở package được chỉ định của module nguồn cho module đích trong lần chạy đó. Nó hữu ích cho cấu hình môi trường, kiểm thử hoặc tương thích tạm thời, nhưng không thay thế quyết định thiết kế module descriptor trong thư viện được phân phối.

Đừng nhầm `--add-opens` với `--add-exports`: tùy chọn thứ nhất cấp quyền deep reflection; tùy chọn thứ hai bổ sung khả năng truy cập kiểu public của package theo cơ chế export.

## 8. Những nhầm lẫn thường gặp

1. **Tưởng open module xuất mọi package.** Mọi package được mở cho reflection, nhưng vẫn cần `exports` để dùng kiểu public theo cách thông thường.
2. **Tưởng mở package đồng nghĩa với public API.** Package không được export vẫn không thể import trực tiếp từ module khác.
3. **Tưởng `opens` và `exports` thay thế được nhau.** Hai directive bảo vệ và cấp quyền ở hai cơ chế khác nhau.
4. **Thêm `opens` vào open module.** Đây là khai báo không hợp lệ vì open module đã mở toàn bộ package.
5. **Tưởng reflection luôn được phép chỉ vì class đã được tìm thấy.** Việc tìm thấy class và việc được truy cập thành viên sâu là hai bước khác nhau; module sở hữu package phải mở package phù hợp.
6. **Mở toàn bộ module cho một framework duy nhất.** Nếu chỉ một package cần reflection, qualified opens thường có phạm vi phù hợp hơn.
7. **Tưởng `open module` là một cơ chế bảo mật cho phép truy cập tùy ý.** Nó nới lỏng ranh giới encapsulation có chủ đích; ứng dụng vẫn phải tuân thủ các quy tắc reflection và quyền truy cập còn lại của Java.

## Ghi nhớ

- `exports`: cho phép module khác dùng các kiểu public của package theo cách thông thường.
- `opens`: cho phép deep reflection vào package ở runtime.
- `open module`: mở tất cả package của một named module cho deep reflection.
- `opens package to module`: mở đúng package cho module tiêu thụ được chỉ định.

Khi gặp lỗi `InaccessibleObjectException`, hãy xác định module sở hữu class, package chứa thành viên cần truy cập và module đang thực hiện reflection. Sau đó chọn `opens` có phạm vi vừa đủ hoặc `open module` nếu thực sự cần mở toàn bộ package.