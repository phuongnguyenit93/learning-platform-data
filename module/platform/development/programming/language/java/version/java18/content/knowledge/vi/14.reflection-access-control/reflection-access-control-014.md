# Xác minh quyền với các fixture cùng module, khác module, package export và package mở

## 1. Mục tiêu và bối cảnh

Bài học thuộc chương **Quyền reflection** của module **JAVA_VERSION_JAVA18**. Java 18 thay đổi cách triển khai core reflection bên trong JDK (JEP 416), nhưng hợp đồng công khai của `java.lang.reflect.Field`, `Constructor`, `AccessibleObject` và Java Platform Module System (JPMS) vẫn là cơ sở cần kiểm chứng trên các phiên bản JDK hiện đại.

Mục tiêu là dựng những **fixture nhỏ, có thể lặp lại** để kiểm tra từng ranh giới truy cập:

- Đọc trường `private` bằng reflection từ **lớp khác package nhưng cùng named module**.
- Đọc trường `public` và thử mở quyền tới trường `private` của **package đã `exports`** cho module khác.
- Thực hiện deep reflection với **package có `opens ... to ...`**.
- Quan sát package **không `exports` và cũng không `opens`**, dù có thể lấy được metadata qua `Class.forName`.
- Ghi nhận riêng kết quả của `Field.canAccess`, `trySetAccessible`, `get` và ngoại lệ, thay vì chỉ dựa vào việc `getDeclaredField` thành công.

**Ràng buộc phiên bản:** Các ví dụ sử dụng API công khai còn được hỗ trợ, chạy trên JDK 18 hoặc JDK hiện đại phù hợp. Không dùng `sun.misc.Unsafe`, tùy chọn `--illegal-access` lỗi thời hoặc thủ thuật phá encapsulation của JDK.

## 2. Hiểu đúng ba lớp quyền

Reflection và JPMS có ba câu hỏi khác nhau:

1. **Có tìm được metadata không?** `Class.forName(...)`, `getDeclaredField(...)` và `getDeclaredConstructor(...)` có thể trả về đối tượng phản chiếu dù mã gọi chưa được phép truy cập member.
2. **Có truy cập theo quy tắc Java thông thường không?** `Field.get(...)`, `set(...)` và `Constructor.newInstance(...)` kiểm tra quyền nếu chưa bật chế độ bỏ qua kiểm tra truy cập thông thường.
3. **Có được phép yêu cầu deep reflection không?** `trySetAccessible()` thử bật chế độ bỏ qua kiểm tra truy cập của `AccessibleObject`. Khả năng bật phụ thuộc vào vị trí module, visibility và việc package có được mở cho module gọi hay không.

Hai chỉ thị trong `module-info.java` có ý nghĩa khác nhau:

| Chỉ thị | Tác dụng chính | Khi module khác muốn đọc trường `private` |
| --- | --- | --- |
| `exports p;` | Cho phép module đọc phụ thuộc sử dụng kiểu `public` và member `public` của package `p` theo quy tắc Java thông thường. | **Không đủ** để bật `trySetAccessible()` trên trường `private`. |
| `opens p to m;` | Cho phép module `m` sử dụng deep reflection vào package `p`. | Có thể `trySetAccessible()` với trường `private` khi các điều kiện API khác hợp lệ. |
| Không `exports`, không `opens` | Giữ kín package với module khác. | Không thể tự ý bật quyền truy cập tới member bằng `trySetAccessible()`. |

Lưu ý:

- `opens` **không** thay thế `exports` cho việc import và sử dụng trực tiếp kiểu trong mã nguồn của module khác.
- `exports` **không** cho phép tự động truy cập member `private` bằng reflection.
- Bên trong **cùng một named module**, `trySetAccessible()` có thể bật quyền cho member `private` của lớp thuộc module đó, dù hai lớp nằm ở các package khác nhau. Việc cùng module không biến truy cập `private` thành hợp lệ theo cú pháp Java thông thường.
- Để sử dụng trực tiếp kiểu `public` của module khác, module gọi cần quan hệ đọc (ví dụ `requires demo.target;`) và package được export phù hợp.

## 3. Ma trận fixture sẽ kiểm chứng

Chúng ta dùng hai named module, `demo.target` chứa các fixture và `demo.probe` là bên gọi từ module khác.

| Fixture và vị trí | Module thực hiện kiểm tra | Trường được thử | Kỳ vọng |
| --- | --- | --- | --- |
| `LocalFixture` trong package nội bộ | **Cùng `demo.target`**, khác package | `private secret` | `get` ban đầu bị từ chối; `trySetAccessible() == true`. |
| `ExportedFixture` trong `demo.target.api` (đã export) | `demo.probe` | `public publicValue` | Đọc trực tiếp qua `Field.get` thành công. |
| `ExportedFixture` | `demo.probe` | `private secret` | `trySetAccessible() == false` nếu package chỉ export. |
| `OpenFixture` trong `demo.target.open` (mở riêng cho `demo.probe`) | `demo.probe` | Constructor và `private secret` | `trySetAccessible() == true`, có thể tạo đối tượng và đọc trường bằng reflection. |
| `ClosedFixture` trong `demo.target.closed` | `demo.probe` | Constructor và `private secret` | `trySetAccessible() == false`. |

Các dự đoán này giả định chạy lệnh trong bài, module descriptor đúng như được cung cấp, không có `--add-opens` bổ sung và không có cơ chế cấp quyền đặc biệt từ môi trường.

## 4. Cấu trúc mã nguồn

Tạo các file theo cây sau, ngay dưới thư mục bài thực hành:

```text
src/
├── demo.target/
│   ├── module-info.java
│   └── demo/target/
│       ├── api/ExportedFixture.java
│       ├── open/OpenFixture.java
│       ├── closed/ClosedFixture.java
│       ├── internal/LocalFixture.java
│       └── local/SameModuleProbe.java
└── demo.probe/
    ├── module-info.java
    └── demo/probe/CrossModuleProbe.java
```

### 4.1. Module chứa fixture

File `src/demo.target/module-info.java`:

```java
module demo.target {
    exports demo.target.api;
    opens demo.target.open to demo.probe;
}
```

Ở đây:

- `demo.target.api` được export, cho phép `demo.probe` dùng lớp `public` trực tiếp.
- `demo.target.open` chỉ được mở cho `demo.probe`; nó không được export.
- `demo.target.internal` và `demo.target.closed` đều không export/open. Chúng có cùng định nghĩa module, nhưng được quan sát từ hai phía khác nhau.

File `src/demo.target/demo/target/internal/LocalFixture.java`:

```java
package demo.target.internal;

public final class LocalFixture {
    private String secret = "same-module";

    public LocalFixture() {
    }
}
```

File `src/demo.target/demo/target/api/ExportedFixture.java`:

```java
package demo.target.api;

public final class ExportedFixture {
    public String publicValue = "exported-public";
    private String secret = "exported-private";

    public ExportedFixture() {
    }
}
```

File `src/demo.target/demo/target/open/OpenFixture.java`:

```java
package demo.target.open;

public final class OpenFixture {
    private String secret = "opened-private";

    public OpenFixture() {
    }
}
```

File `src/demo.target/demo/target/closed/ClosedFixture.java`:

```java
package demo.target.closed;

public final class ClosedFixture {
    private String secret = "closed-private";

    public ClosedFixture() {
    }
}
```

Tất cả trường `secret` trong ví dụ cố ý **không phải `final`** để phép thử chỉ đo quyền truy cập. Hợp đồng ghi vào `final` có các giới hạn riêng trên JDK hiện đại, không nên trộn vào phép thử này.

### 4.2. Probe ở một package khác nhưng cùng module

File `src/demo.target/demo/target/local/SameModuleProbe.java`:

```java
package demo.target.local;

import demo.target.internal.LocalFixture;
import java.lang.reflect.Field;

public final class SameModuleProbe {
    public static void main(String[] args) throws ReflectiveOperationException {
        LocalFixture fixture = new LocalFixture();
        Field field = LocalFixture.class.getDeclaredField("secret");

        System.out.println("same/private canAccess before: "
                + field.canAccess(fixture));

        try {
            field.get(fixture);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("same/private direct: IllegalAccessException");
        }

        boolean enabled = field.trySetAccessible();
        System.out.println("same/private trySetAccessible: " + enabled);

        if (enabled) {
            System.out.println("same/private value: " + field.get(fixture));
            field.set(fixture, "updated-in-same-module");
            System.out.println("same/private updated: " + field.get(fixture));
        }
    }
}
```

`SameModuleProbe` và `LocalFixture` nằm trong các package khác nhau nhưng cùng `demo.target`. Vì trường `secret` là `private`, lời gọi `get` ban đầu không vượt qua kiểm tra truy cập thông thường. `trySetAccessible()` thành công vì module gọi và module khai báo trường là một.

Việc lớp `LocalFixture` không thuộc package export **không ngăn** mã trong cùng module import và dùng lớp `public` này.

### 4.3. Probe từ module khác

File `src/demo.probe/module-info.java`:

```java
module demo.probe {
    requires demo.target;
}
```

File `src/demo.probe/demo/probe/CrossModuleProbe.java`:

```java
package demo.probe;

import demo.target.api.ExportedFixture;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class CrossModuleProbe {
    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println("Target module resolved: "
                + ModuleLayer.boot().findModule("demo.target").isPresent());

        // Package public API: exported nhưng không opened.
        ExportedFixture exported = new ExportedFixture();
        Field exportedPublic =
                ExportedFixture.class.getDeclaredField("publicValue");
        Field exportedPrivate =
                ExportedFixture.class.getDeclaredField("secret");

        System.out.println("export/public canAccess: "
                + exportedPublic.canAccess(exported));
        System.out.println("export/public value: "
                + exportedPublic.get(exported));

        System.out.println("export/private canAccess: "
                + exportedPrivate.canAccess(exported));
        try {
            exportedPrivate.get(exported);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("export/private direct: IllegalAccessException");
        }

        boolean exportedEnabled = exportedPrivate.trySetAccessible();
        System.out.println("export/private trySetAccessible: "
                + exportedEnabled);
        if (exportedEnabled) {
            System.out.println("export/private value: "
                    + exportedPrivate.get(exported));
        }

        // Package chỉ opened: dùng tên lớp, không import trực tiếp.
        Class<?> openedClass =
                Class.forName("demo.target.open.OpenFixture");
        Constructor<?> openedCtor = openedClass.getDeclaredConstructor();
        boolean ctorEnabled = openedCtor.trySetAccessible();
        System.out.println("open/ctor trySetAccessible: " + ctorEnabled);
        if (!ctorEnabled) {
            throw new AssertionError("Expected opened constructor access");
        }

        Object opened = openedCtor.newInstance();
        Field openedPrivate = openedClass.getDeclaredField("secret");
        System.out.println("open/private canAccess before: "
                + openedPrivate.canAccess(opened));
        boolean openedEnabled = openedPrivate.trySetAccessible();
        System.out.println("open/private trySetAccessible: " + openedEnabled);
        if (openedEnabled) {
            System.out.println("open/private value: "
                    + openedPrivate.get(opened));
            openedPrivate.set(opened, "updated-across-modules");
            System.out.println("open/private updated: "
                    + openedPrivate.get(opened));
        }

        // Package neither exported nor opened: xem metadata được,
        // nhưng không tự động được phép truy cập vào member.
        Class<?> closedClass =
                Class.forName("demo.target.closed.ClosedFixture");
        Constructor<?> closedCtor = closedClass.getDeclaredConstructor();
        System.out.println("closed/ctor trySetAccessible: "
                + closedCtor.trySetAccessible());
        Field closedPrivate = closedClass.getDeclaredField("secret");
        System.out.println("closed/private trySetAccessible: "
                + closedPrivate.trySetAccessible());
    }
}
```

Trong đoạn này, `demo.probe` chỉ import `demo.target.api.ExportedFixture` vì package đó đã export. Lớp ở package `open` và `closed` được tìm qua tên bằng `Class.forName`, cho phép kiểm tra khả năng lấy metadata và mở quyền bằng reflection mà không phụ thuộc vào việc import được chúng ở compile time.

`getDeclaredConstructor` và `getDeclaredField` có thể trả metadata ngay cả khi `trySetAccessible` không được phép. Đó chính là điểm cần quan sát, thay vì mặc định cho rằng tìm thấy metadata nghĩa là gọi `get` hoặc `newInstance` sẽ thành công.

## 5. Biên dịch và chạy trên JDK thực tế

Kiểm tra bộ công cụ đang hoạt động:

```shell
java -version
javac -version
```

Từ thư mục chứa `src`, biên dịch đồng thời hai named module:

```shell
javac --module-source-path src -d mods -m demo.target,demo.probe
```

Chạy probe ở **cùng module**:

```shell
java --module-path mods --module demo.target/demo.target.local.SameModuleProbe
```

Dấu hiệu kết quả mong đợi:

```text
same/private canAccess before: false
same/private direct: IllegalAccessException
same/private trySetAccessible: true
same/private value: same-module
same/private updated: updated-in-same-module
```

Chạy probe từ **module khác**:

```shell
java --module-path mods --show-module-resolution --module demo.probe/demo.probe.CrossModuleProbe
```

Dấu hiệu kết quả mong đợi khi dùng descriptor trong bài:

```text
Target module resolved: true
export/public canAccess: true
export/public value: exported-public
export/private canAccess: false
export/private direct: IllegalAccessException
export/private trySetAccessible: false
open/ctor trySetAccessible: true
open/private canAccess before: false
open/private trySetAccessible: true
open/private value: opened-private
open/private updated: updated-across-modules
closed/ctor trySetAccessible: false
closed/private trySetAccessible: false
```

`--show-module-resolution` in thêm các dòng mô tả module được resolve nên đầu ra toàn bộ có thể dài hơn ví dụ. Log này xác nhận module tham gia quá trình chạy; các dòng `canAccess`/`trySetAccessible` xác nhận **quyền cụ thể với member**.

Các lệnh đều nằm trên một dòng, có thể sử dụng trong PowerShell hoặc terminal tương đương. Nếu terminal báo không tìm thấy `demo.target` hoặc `demo.probe`, kiểm tra tên module, cấu trúc `src`, kết quả biên dịch trong `mods` và `java --module-path`.

## 6. Phân tích từng kết quả và phạm vi áp dụng

### 6.1. Cùng module không đồng nghĩa bỏ qua `private` tự động

Trong `SameModuleProbe`, `field.get(fixture)` ban đầu bị từ chối vì lớp gọi và lớp khai báo là hai lớp khác nhau, ở các package khác nhau. Khi `trySetAccessible()` trả `true`, các phép `get` và `set` tiếp theo dùng cùng `Field` đã được bật chế độ bỏ qua kiểm tra truy cập thông thường.

Đây là hành vi được hỗ trợ cho các lớp trong cùng module; không phải yêu cầu thêm `exports demo.target.internal` để đọc từ `demo.target.local`.

### 6.2. Export cho phép truy cập API public; private vẫn bị bảo vệ

Trong `CrossModuleProbe`, module gọi có `requires demo.target`. Vì `demo.target.api` đã export, `ExportedFixture` và trường `publicValue` có thể dùng qua cú pháp Java và reflection.

Ngược lại, `private secret` trong cùng lớp không được công khai do `exports`; `trySetAccessible()` trả `false` khi package không được mở cho module gọi.

Một trường `public` nằm trong một lớp `public` ở package export có thể được đọc bằng `get` mà không cần `trySetAccessible`. Việc dùng reflection không tự làm tăng yêu cầu phải mở package cho mọi thao tác.

### 6.3. Opens cấp quyền deep reflection đến đúng module đích

Khai báo:

```java
opens demo.target.open to demo.probe;
```

cho phép mã trong `demo.probe` yêu cầu bỏ kiểm tra truy cập đối với constructor và field của lớp trong package này, như ví dụ `trySetAccessible()` cho constructor và `private secret`.

Nếu viết `import demo.target.open.OpenFixture;` trong mã của `demo.probe`, việc biên dịch sẽ thất bại vì package không export. Ví dụ cố ý dùng `Class.forName` để thể hiện sự khác nhau giữa **khả năng truy cập bằng tên kiểu ở compile time** và **khả năng deep reflection tại runtime**.

### 6.4. Package đóng vẫn có thể trả metadata

Ở `demo.target.closed`, `Class.forName` có thể tìm lớp và `getDeclaredField("secret")` có thể trả `Field` khi module đã được resolve và class loader tìm thấy lớp. Nhưng trong phép thử này, package không export/open, nên module khác không được phép tự bật quyền tới constructor và trường private: `trySetAccessible()` trả `false`.

Đừng nhầm `ClassNotFoundException` (không tìm được lớp) với `IllegalAccessException` (không được phép truy cập member) hay kết quả `trySetAccessible() == false` (không được phép bật bỏ kiểm tra truy cập). Đây là các giai đoạn khác nhau.

## 7. Thử thay đổi đúng một điều kiện: mở package export bằng tham số JVM

Bạn có thể thực hiện **một lượt chạy so sánh** sau khi đã lưu đầu ra baseline:

```shell
java --module-path mods --add-opens demo.target/demo.target.api=demo.probe --module demo.probe/demo.probe.CrossModuleProbe
```

Lúc này `demo.target.api` được mở thêm cho `demo.probe` **trong tiến trình đó**, vì vậy dòng `export/private trySetAccessible` có thể đổi từ `false` thành `true`, và chương trình sẽ in thêm giá trị `export/private value`.

Lưu ý phạm vi tác động:

- `--add-opens` phục vụ kiểm chứng cấu hình hoặc tích hợp trong trường hợp cần thiết. Với mã bạn kiểm soát, ưu tiên khai báo `opens ... to ...` có phạm vi rõ ràng trong module descriptor.
- Việc mở `demo.target.api` **không** đồng thời mở `demo.target.closed`.
- `--add-exports` chỉ tác động đến khả năng truy cập kiểu/member public theo quy tắc export; nó không tương đương với `--add-opens` đối với trường `private`.
- Nếu chạy test trong IDE, Maven hoặc môi trường triển khai khác, phải ghi lại chính xác module path và JVM options của tiến trình thử nghiệm. Kết luận dựa trên một shell có `--add-opens` không đại diện cho mọi môi trường.

Đây cũng là cách xây dựng một kiểm thử tích hợp: khởi chạy mỗi cấu hình ở một JVM mới, kiểm tra các dòng có giá trị boolean và ngoại lệ, rồi so sánh giữa các cấu hình.

## 8. `canAccess`, `trySetAccessible` và `setAccessible`: dùng đúng mục đích

| API | Điều cần biết | Kết quả liên quan |
| --- | --- | --- |
| `field.canAccess(receiver)` | Kiểm tra xem **caller hiện tại** có thể truy cập field đã được chỉ ra không; cũng xét việc bật chế độ bỏ kiểm tra truy cập trên `Field`. | Trả về `boolean`; receiver không hợp lệ có thể gây `IllegalArgumentException`. |
| `field.trySetAccessible()` | Thử bật cờ bỏ kiểm tra truy cập thông thường; chịu giới hạn module, visibility và quyền sâu reflection. | `true` khi bật được, `false` khi JPMS không cho phép bật. |
| `field.setAccessible(true)` | Yêu cầu bật chế độ tương ứng, nhưng báo lỗi nếu module không cho phép. | Có thể ném `java.lang.reflect.InaccessibleObjectException`. |
| `field.get(receiver)` / `field.set(receiver, value)` | Thao tác thực tế với member, bao gồm kiểm tra quyền và receiver/kiểu giá trị. | Có thể ném `IllegalAccessException`, `IllegalArgumentException`, `NullPointerException` tùy nguyên nhân. |

`canAccess` trả lời về quyền truy cập **ở thời điểm gọi**. Hãy cung cấp đúng receiver: instance field cần đối tượng đúng kiểu, static field cần `null`. Một receiver sai không phải là phép thử tốt về `exports` hoặc `opens`.

`trySetAccessible` không làm thay đổi `module-info.java`; nó chỉ thay đổi trạng thái bỏ kiểm tra truy cập của đối tượng `AccessibleObject` đang sử dụng khi được phép. Cũng không đảm bảo mọi phép ghi đều hợp lệ: các quy tắc kiểu dữ liệu, trường `final` và bất biến của JVM vẫn có hiệu lực.

## 9. Chú ý riêng về `final` và giới hạn API hiện đại

Để ma trận ở bài này ổn định, tất cả trường thử ghi đều là trường thường. Với `final`, đặc biệt `static final`, các trường trong record và một số cấu trúc đặc biệt của JVM, quyền ghi bằng reflection chịu hạn chế riêng. Một `Field` có thể được dùng để đọc nhờ `trySetAccessible()` nhưng việc `set` vẫn bị từ chối.

Do đó:

- Dùng reflection đọc metadata hoặc thực hiện thao tác được mô tả rõ trong API khi có lý do chính đáng.
- Không suy diễn `trySetAccessible() == true` thành quyền sửa mọi trường `final`.
- Tránh dựa vào việc can thiệp trạng thái bất biến để thiết kế chức năng sản phẩm hoặc bài kiểm thử.

Giới hạn chính xác có thể thay đổi theo các phiên bản JDK hiện đại; hãy đối chiếu Javadoc của `Field.set`/`AccessibleObject` ứng với **đúng JDK đang chạy** trước khi xây dựng code phụ thuộc vào `final`.

## 10. Khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân phổ biến | Cách xác minh |
| --- | --- | --- |
| `package demo.target.open is not visible` khi import | Package chỉ `opens`, không `exports` cho mã Java thông thường. | Dùng `Class.forName` trong bài thử reflection hoặc export API thích hợp nếu thiết kế thực sự cần import. |
| `NoSuchFieldException` | Tên field sai, field nằm ở lớp cha nhưng dùng `getDeclaredField`, hoặc không có khai báo đó. | Kiểm tra tên trường và lớp khai báo. |
| `IllegalAccessException` từ `Field.get` | Caller không có quyền truy cập thông thường; chưa bật quyền phản chiếu thích hợp. | Kiểm tra `canAccess`, `trySetAccessible`, `module-info.java`. |
| `trySetAccessible() == false` | Caller từ module khác không có điều kiện truy cập hoặc package chưa được opened đúng nơi. | Xác nhận module của caller, `opens ... to ...`, đối chiếu `--add-opens`. |
| `InaccessibleObjectException` từ `setAccessible(true)` | JPMS từ chối mở quyền truy cập. | Ưu tiên `trySetAccessible` để kiểm chứng khả năng truy cập và điều chỉnh thiết kế/cấu hình hợp lệ. |
| `IllegalArgumentException` từ `canAccess` hoặc `get`/`set` | Receiver sai loại; `canAccess(null)` với instance field hoặc `canAccess(nonNull)` với static field; `set` cũng có thể nhận value sai kiểu. | Kiểm tra loại field, receiver thực tế và kiểu giá trị. |
| `NullPointerException` từ `get`/`set` | Gọi `get(null)` hoặc `set(null, value)` trên instance field. | Truyền receiver khác `null` và đúng kiểu. |
| `ClassNotFoundException` | Tên lớp sai hoặc class loader/module path không có module mục tiêu phù hợp. | Kiểm tra cách biên dịch, tên binary class và module resolution. |
| `Module ... not found` | Thiếu module trên module path hoặc tên module sai. | Kiểm tra lệnh `javac`, `java --module-path mods` và `requires`. |

Trong môi trường thực tế, hãy lưu `java -version`, lệnh chạy đầy đủ và descriptor liên quan của hai module. Nếu kết quả khác với ma trận, trước tiên kiểm tra JVM options, phiên bản JDK, cách build và class loader thay vì lập tức cho rằng hợp đồng reflection đã thay đổi.

## 11. Bài tập và câu hỏi tự kiểm tra

### Bài tập

1. Chạy cả `SameModuleProbe` và `CrossModuleProbe`; ghi lại `canAccess`, `trySetAccessible` và ngoại lệ tương ứng.
2. Thay `opens demo.target.open to demo.probe;` bằng `exports demo.target.open;` trong fixture, biên dịch và chạy lại. Giải thích vì sao export riêng không mở quyền cho trường `private`.
3. Khôi phục descriptor gốc, sau đó dùng `--add-opens demo.target/demo.target.api=demo.probe` và so sánh đúng dòng `export/private trySetAccessible` giữa hai lần chạy.
4. Thêm một lớp gọi trong cùng `demo.target` nhưng ở package khác để kiểm chứng `LocalFixture`; xác nhận không cần export package nội bộ cho module của chính nó.
5. Thử gọi `setAccessible(true)` với `exportedPrivate` khi package chỉ export. Ghi lại lớp ngoại lệ (nếu có) và giải thích kết quả bằng JPMS.

### Câu hỏi

**1. Vì sao `getDeclaredField("secret")` thành công không có nghĩa được phép gọi `get`?**

Vì lấy metadata và truy cập giá trị là hai bước khác nhau. Truy cập giá trị phải đáp ứng quy tắc Java hoặc được phép bật chế độ bỏ qua kiểm tra truy cập thông thường.

**2. Cùng module thì có thể đọc mọi field private ngay bằng `Field.get` không?**

Không. Nếu caller không có quyền Java thông thường đối với trường private, cần một bước hợp lệ như `trySetAccessible()`. Với cùng module, bước này thường được phép theo hợp đồng `AccessibleObject`.

**3. `exports` và `opens` khác nhau ở đâu trong bài này?**

`exports` cho phép sử dụng API public từ module khác có quyền đọc; `opens` cho phép deep reflection của module được mở tới, kể cả member không public, theo các giới hạn API hiện hành.

**4. Package chỉ `opens` có thể được import trực tiếp bởi module khác không?**

Không chỉ nhờ `opens`. Muốn dùng kiểu như API Java thông thường cần `exports` phù hợp và quan hệ đọc module. Mục đích của `opens` là reflection.

**5. Có nên cấu hình `--add-opens` toàn bộ package để làm mọi phép thử pass không?**

Không. Hãy xác định API nào thực sự cần deep reflection, mở đúng package cho đúng module và giữ các trường hợp bị từ chối để xác minh ranh giới truy cập.

## Tài liệu tham khảo

- Java SE API — `AccessibleObject` và `trySetAccessible`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE API — `Field`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html
- Java SE API — `Constructor`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html
- Java Language Specification — Module Declarations: https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7
- OpenJDK JEP 416 — *Reimplement Core Reflection with Method Handles*: https://openjdk.org/jeps/416

Các liên kết Java SE 25 dùng để tham khảo API công khai trên JDK hiện đại. Khi kiểm chứng một môi trường cụ thể, hãy đối chiếu tài liệu tương ứng với **phiên bản JDK thực sự chạy ứng dụng**.
