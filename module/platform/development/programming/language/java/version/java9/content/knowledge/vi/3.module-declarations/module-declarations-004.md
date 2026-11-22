# Khai báo open module và phạm vi mở phản chiếu

JPMS kiểm soát hai loại truy cập khác nhau: truy cập API thông thường giữa các module và truy cập sâu bằng reflection. `exports` công bố package để mã ở module khác dùng các kiểu public; `opens` cho phép mã ở module được chỉ định truy cập sâu qua reflection vào package. Nếu mở toàn bộ module bằng `open module`, mọi package trong module đều được mở cho reflection.

Việc chọn phạm vi mở cần bám theo nhu cầu thực tế của framework hoặc thành phần phản chiếu. Mở đúng package và đúng module giúp giữ phần triển khai kín, giảm phụ thuộc vào chi tiết nội bộ và duy trì ranh giới JPMS rõ ràng.

Nội dung dưới đây tập trung vào cú pháp và hành vi JPMS hiện hành. Ví dụ chạy được bằng Java 17 trở lên.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích mục đích của `open module` và directive `opens`.
- Phân biệt `opens` với `exports` và hiểu vì sao mở package không đồng nghĩa với công bố API.
- Chọn giữa `opens package;`, `opens package to module;` và `open module`.
- Hiểu cách reflection dùng `trySetAccessible()`, constructor và field trong module.
- Sử dụng `--add-opens` đúng mục đích khi cần cấu hình runtime.
- Kiểm tra lỗi truy cập phản chiếu và giới hạn phạm vi mở một cách có kiểm soát.

## 1. Vì sao JPMS cần cơ chế mở reflection?

### 1.1. Đóng gói mạnh và reflection

Một module thường giữ class triển khai trong package không export. Điều này ngăn module khác truy cập trực tiếp các kiểu trong package đó theo quy tắc truy cập Java thông thường.

Tuy nhiên, một số thư viện cần reflection để thực hiện công việc của chúng. Ví dụ, một thư viện ánh xạ JSON có thể cần đọc field, một dependency injection container có thể cần gọi constructor, hoặc một ORM có thể cần tạo đối tượng và đọc trạng thái thông qua metadata.

Nếu package chỉ được giữ kín, module khác có thể không truy cập sâu vào thành viên private. JPMS cung cấp `opens` để module chủ động cho phép loại truy cập phản chiếu này.

### 1.2. Truy cập API và truy cập sâu là hai nhu cầu khác nhau

Hãy phân biệt:

- Ứng dụng gọi một method public đã được module công bố: đây là sử dụng API.
- Framework tìm private field, private constructor hoặc method nội bộ qua reflection: đây là truy cập sâu.
- Ứng dụng muốn import một class trong package không export: đây là truy cập mã thông thường và không được cấp chỉ vì package đã được mở.

`opens` phục vụ nhu cầu thứ hai. Nó không biến package thành API công khai và không thay thế `exports`.

## 2. Phân biệt exports và opens

| Khả năng | `exports` | `opens` |
| --- | --- | --- |
| Cho module khác dùng kiểu public trong package theo cách thông thường | Có | Không |
| Cho phép truy cập public API qua biên module | Có | Không tự cấp quyền này |
| Cho phép reflection sâu vào thành viên không public | Không, chỉ export là chưa đủ | Có, theo phạm vi được mở |
| Dùng để công bố hợp đồng API | Có | Không |
| Có thể giới hạn cho module đích | Có, qualified exports | Có, qualified opens |

Một package có thể vừa được export vừa được open nếu nó có cả hai nhu cầu. Ví dụ, package API cần được ứng dụng gọi bình thường và một framework cụ thể cần truy cập sâu. Trong trường hợp đó, hai directive diễn đạt hai quyền riêng biệt.

### 2.1. exports

Ví dụ:

~~~java
module customer.api {
    exports com.acme.customer.api;
}
~~~

Module khác có thể khai báo `requires customer.api;` và sử dụng các kiểu public thuộc package đã export. Các thành viên private vẫn được bảo vệ; `exports` không tự cho phép framework đọc hoặc sửa field private bằng reflection sâu.

Có thể giới hạn export cho một hoặc một số module:

~~~java
module customer.api {
    exports com.acme.customer.api to customer.app;
}
~~~

Đây là qualified exports. Nó giới hạn module được truy cập API theo cách thông thường.

### 2.2. opens

Mở một package cho tất cả module ở thời điểm chạy:

~~~java
module customer.model {
    opens com.acme.customer.internal;
}
~~~

Mở package cho một module cụ thể:

~~~java
module customer.model {
    opens com.acme.customer.internal to customer.mapper;
}
~~~

Directive thứ hai là qualified opens. Chỉ module `customer.mapper` được cấp quyền truy cập sâu bằng reflection vào package đó.

Mở package không export package cho mã Java thông thường. Nếu `customer.app` cần import một kiểu public trong package, module vẫn phải export package đó theo cách phù hợp.

### 2.3. Phạm vi của qualified opens

Qualified opens là lựa chọn nên cân nhắc khi biết rõ module nào cần reflection. Nó giúp giới hạn quyền truy cập vào package và tránh mở toàn bộ nội bộ cho mọi module.

Tên module đích phải khớp với tên module trong module descriptor của thành phần sử dụng. Nếu framework chạy trong unnamed module trên classpath, có thể dùng `ALL-UNNAMED` với tùy chọn dòng lệnh `--add-opens`; module descriptor không khai báo `ALL-UNNAMED` như một tên module thông thường.

## 3. open module: mở toàn bộ package

### 3.1. Cú pháp

Một module có thể được khai báo là open:

~~~java
open module customer.model {
    requires java.sql;
    exports com.acme.customer.api;
}
~~~

Từ khóa `open` ở đầu module declaration làm cho tất cả package trong module được mở cho deep reflection từ các module khác. Điều này áp dụng cả package hiện tại lẫn package được thêm về sau.

Một open module vẫn có thể dùng `exports` để công bố API thông thường. Hai cơ chế vẫn khác nhau: `open` mở reflection trên toàn bộ package; `exports` cho phép truy cập kiểu public theo quy tắc module.

### 3.2. open module không có nghĩa là export mọi package

Đây là điểm dễ nhầm:

- Mọi package của open module được mở cho reflection.
- Package không tự động được export.
- Module khác vẫn không thể import kiểu trong package không export như API thông thường.
- Module vẫn khai báo dependency bằng `requires`, và có thể khai báo `uses` hoặc `provides` khi cần.

Open module không nên được dùng chỉ để "làm cho mọi lỗi truy cập biến mất". Nó mở phạm vi reflection rất rộng và làm giảm lợi ích đóng gói mạnh của JPMS.

### 3.3. Giới hạn của open module

Khi module đã dùng từ khóa `open`, không khai báo thêm các directive `opens` riêng lẻ trong module descriptor. Tất cả package đã được mở bởi chính khai báo module; nếu cần chọn package hoặc module đích, hãy dùng một module thông thường với các directive `opens` cụ thể.

Dùng open module khi gần như mọi package trong module thực sự cần được framework hoặc thành phần phản chiếu truy cập sâu. Nếu chỉ một vài package cần reflection, qualified opens thường diễn đạt ý định chính xác hơn.

## 4. Reflection hoạt động thế nào với opens?

### 4.1. Lấy metadata và truy cập thành viên là hai bước khác nhau

Reflection có thể tìm class, constructor, method hoặc field bằng các API như:

- `Class.forName(...)`
- `getDeclaredConstructor(...)`
- `getDeclaredMethod(...)`
- `getDeclaredField(...)`

Việc lấy metadata không đồng nghĩa với việc được phép truy cập sâu vào thành viên. Trước khi gọi constructor hoặc đọc field không public qua ranh giới module, mã phản chiếu cần có quyền phù hợp.

Từ Java 9, `AccessibleObject.trySetAccessible()` cho phép thử bật quyền truy cập. Nó trả về `true` khi quyền truy cập có thể được bật; nếu package không được mở phù hợp, nó trả về `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException` khi không thể vượt qua kiểm tra module.

### 4.2. Điều kiện để reflection truy cập sâu

Với một package thuộc named module khác, deep reflection cần package đó được mở cho module đang thực hiện reflection. Việc mở có thể đến từ:

- `opens package;` trong module descriptor.
- `opens package to target.module;` nếu module gọi là target được chỉ định.
- `open module ...` nếu toàn module được mở.
- Tùy chọn runtime `--add-opens` khi khởi chạy.

Ngoài quyền mở package, ứng dụng vẫn cần một cách tìm và sử dụng đối tượng phù hợp. `opens` không tự tạo instance, không thay thế dependency injection, và không làm cho một module khác tự động trở thành dependency ở cấp kiến trúc.

### 4.3. Ví dụ lỗi truy cập

Giả sử module `model.module` có class `Person` với field private. Nếu package không được mở cho module gọi, `trySetAccessible()` không thể cấp quyền truy cập sâu vào field đó. Khi dùng `setAccessible(true)`, chương trình có thể nhận `InaccessibleObjectException`.

Cách xử lý đúng là xác định module thực sự cần reflection và mở package cần thiết cho module đó, sau khi cân nhắc API có thể thay thế việc truy cập sâu hay không.

## 5. Ví dụ chạy được: qualified opens cho một module cụ thể

Ví dụ có hai module:

- `model.module`: chứa class Person trong package nội bộ, không export package.
- `inspector.app`: dùng reflection để tạo Person và đọc field private.

Cấu trúc thư mục:

~~~text
src/
├── model.module/
│   ├── module-info.java
│   └── com/acme/model/internal/Person.java
└── inspector.app/
    ├── module-info.java
    └── com/acme/inspector/Main.java
~~~

### 5.1. Module model.module

File `src/model.module/module-info.java`:

~~~java
module model.module {
    opens com.acme.model.internal to inspector.app;
}
~~~

Package được mở cho riêng `inspector.app`. Nó không được export, vì vậy package vẫn là chi tiết nội bộ khi xét truy cập Java thông thường.

File `src/model.module/com/acme/model/internal/Person.java`:

~~~java
package com.acme.model.internal;

import java.util.Objects;

public final class Person {
    private final String name;

    public Person(String name) {
        this.name = Objects.requireNonNull(name);
    }
}
~~~

### 5.2. Module inspector.app

File `src/inspector.app/module-info.java`:

~~~java
module inspector.app {
    requires model.module;
}
~~~

Ứng dụng khai báo dependency vào module chứa class. Nó không import Person vì package nội bộ không export.

File `src/inspector.app/com/acme/inspector/Main.java`:

~~~java
package com.acme.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.acme.model.internal.Person");

        Constructor<?> constructor =
                type.getDeclaredConstructor(String.class);

        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Constructor package is not open");
        }

        Object person = constructor.newInstance("An");

        Field name = type.getDeclaredField("name");
        if (!name.trySetAccessible()) {
            throw new IllegalStateException(
                    "Field package is not open");
        }

        System.out.println("private name=" + name.get(person));
        System.out.println("model module=" + type.getModule().getName());
    }
}
~~~

Ứng dụng tìm class bằng tên, bật quyền truy cập cho constructor và field, rồi đọc giá trị. Việc này thành công vì package được mở có mục tiêu cho `inspector.app`.

### 5.3. Biên dịch và chạy bằng Java 17+

Từ thư mục chứa `src`:

~~~bash
javac --release 17 --module-source-path src -d out -m model.module,inspector.app
java --module-path out -m inspector.app/com.acme.inspector.Main
~~~

Kết quả stdout:

~~~text
private name=An
model module=model.module
~~~

Nếu bỏ directive `opens com.acme.model.internal to inspector.app;`, `trySetAccessible()` không thể bật truy cập sâu vào constructor và field trong ví dụ này. Package không được export cũng có nghĩa là ứng dụng không thể dùng Person như một kiểu API thông thường.

## 6. So sánh ba cách mở package

| Cách khai báo | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| `opens p;` | Mọi module được reflection vào package p | Nhiều module thực sự cần truy cập sâu cùng package |
| `opens p to m;` | Chỉ module m được reflection vào package p | Biết chính xác framework hoặc module gọi |
| `open module m { }` | Mọi package của module được mở cho mọi module | Hầu hết package đều cần deep reflection |

Khi thiết kế module, hãy bắt đầu từ package và module đích cần quyền truy cập. Chỉ tăng phạm vi khi có yêu cầu cụ thể mà cách mở hẹp hơn không đáp ứng.

## 7. --add-opens khi cần cấu hình lúc khởi chạy

### 7.1. Cú pháp

Tùy chọn `--add-opens` có thể mở một package trong một lần chạy mà không sửa module descriptor:

~~~bash
java --add-opens model.module/com.acme.model.internal=inspector.app --module-path out -m inspector.app/com.acme.inspector.Main
~~~

Cấu trúc tổng quát:

~~~text
--add-opens source.module/package=target.module
~~~

Có thể chỉ định nhiều module đích theo cú pháp của tùy chọn. `ALL-UNNAMED` là đích đặc biệt khi code gọi nằm trong unnamed module, thường là code chạy trên classpath.

### 7.2. Khi nào dùng?

`--add-opens` phù hợp để:

- Xác nhận một framework cần mở package nào.
- Hỗ trợ chuyển đổi một ứng dụng cũ sang JPMS trong lúc chưa thể sửa module descriptor của thư viện.
- Cấu hình một môi trường chạy cụ thể khi thành phần tích hợp có yêu cầu reflection đã biết.

Với ứng dụng do mình kiểm soát, hãy ưu tiên khai báo `opens` rõ trong module descriptor của module sở hữu package. Tùy chọn dòng lệnh là cấu hình của lần khởi chạy, cần được quản lý trong script hoặc cấu hình triển khai.

### 7.3. Những gì --add-opens không làm

- Không thêm dependency `requires`.
- Không export package cho truy cập Java thông thường.
- Không thay đổi mã nguồn hoặc module descriptor.
- Không tự sửa một API được thiết kế sai.
- Không nên được thêm rộng cho nhiều package nếu chưa xác định nhu cầu.

## 8. Cách chọn phạm vi mở trong dự án thực tế

1. Xác định framework hoặc module nào thực hiện reflection.
2. Xác định package cụ thể mà framework cần truy cập.
3. Kiểm tra liệu framework có thể dùng constructor, accessor hoặc API công khai thay cho field private hay không.
4. Nếu cần deep reflection, ưu tiên qualified opens cho module đích.
5. Chỉ dùng `opens p;` khi nhiều module cần truy cập sâu vào cùng package.
6. Chỉ dùng `open module` khi phần lớn hoặc toàn bộ package đều cần được mở.
7. Nếu chưa thể sửa module descriptor, thử `--add-opens` ở môi trường chạy có kiểm soát.
8. Sau khi cấu hình, kiểm thử trên đúng JDK và phiên bản framework dùng trong triển khai.

Mỗi directive mở nên có lý do rõ ràng. Khi framework hoặc tính năng reflection không còn cần một package, hãy thu hẹp hoặc bỏ directive tương ứng.

## 9. Lỗi thường gặp

- **Dùng exports để giải quyết lỗi truy cập private:** export chỉ công bố API public; hãy dùng opens nếu thật sự cần deep reflection.
- **Nghĩ rằng opens cho phép import package:** opens không thay thế exports.
- **Mở toàn bộ module vì một field private:** dùng qualified opens cho package và module đích cụ thể.
- **Quên khai báo requires của ứng dụng:** opens không thay thế dependency module.
- **Không kiểm tra kết quả trySetAccessible():** hãy xử lý trường hợp trả về false trước khi đọc hoặc gọi thành viên.
- **Dùng setAccessible(true) rồi bỏ qua lỗi:** InaccessibleObjectException cho biết ranh giới module chưa cho phép truy cập sâu.
- **Đưa quá nhiều --add-opens vào lệnh chạy:** phạm vi rộng làm giảm tính đóng gói và che giấu dependency phản chiếu.
- **Mở package API và package nội bộ cùng lúc mà không có lý do:** chỉ mở những package thực sự cần framework truy cập sâu.

## 10. Checklist tự đánh giá

- [ ] Giải thích được sự khác nhau giữa exports và opens.
- [ ] Viết được directive `opens package;` và qualified opens.
- [ ] Giải thích được open module mở tất cả package cho deep reflection.
- [ ] Hiểu rằng open module không tự export package.
- [ ] Biết giới hạn của opens trong open module declaration.
- [ ] Dùng được `trySetAccessible()` và xử lý khi kết quả là false.
- [ ] Hiểu vì sao reflection cần package được mở cho module gọi.
- [ ] Biên dịch và chạy được ví dụ hai module.
- [ ] Biết dùng `--add-opens` như cấu hình runtime có phạm vi rõ.
- [ ] Chọn phạm vi mở nhỏ nhất đáp ứng yêu cầu framework.
