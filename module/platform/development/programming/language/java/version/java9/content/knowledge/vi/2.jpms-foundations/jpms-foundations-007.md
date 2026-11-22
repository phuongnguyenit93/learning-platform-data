# Phân biệt đóng gói mạnh với cơ chế cô lập mã không đáng tin cậy

## Mục tiêu

Trong Java Platform Module System (JPMS), **đóng gói mạnh (strong encapsulation)** kiểm soát package và thành viên nào của một module được module khác truy cập. **Cô lập mã không đáng tin cậy (untrusted-code isolation)** kiểm soát những tác động mà chương trình có thể gây ra lên hệ điều hành, dữ liệu và tài nguyên của máy chạy.

Hai cơ chế giải quyết hai bài toán khác nhau. JPMS giúp thiết kế API và ranh giới kiến trúc rõ ràng trong một JVM. Muốn chạy mã có thể độc hại, cần một ranh giới thực thi ở cấp tiến trình/hệ điều hành, thường được củng cố bằng container hoặc máy ảo.

## 1. Đóng gói mạnh trong JPMS

Một module khai báo trong `module-info.java` những module nó phụ thuộc và những package nó cung cấp ra bên ngoài. Với module thông thường:

- `requires` khai báo phụ thuộc và thiết lập quan hệ đọc giữa các module.
- `exports` công khai package cho module khác. Module nhận được quyền truy cập ở thời điểm biên dịch và chạy đối với các kiểu cùng thành viên `public`/ `protected` trong package được xuất, theo quy tắc truy cập Java.
- `opens` cho phép truy cập phản chiếu (reflection) ở thời điểm chạy. Package được mở không vì thế trở thành package có thể import và dùng trực tiếp ở thời điểm biên dịch.
- `exports p to m` và `opens p to m` giới hạn quyền cho module đích được nêu. Đây là cách ưu tiên khi chỉ một framework hoặc module cụ thể cần API hay reflection.
- `open module` mở tất cả package cho reflection ở thời điểm chạy. Chỉ dùng khi có nhu cầu rõ ràng vì phạm vi mở rộng hơn.

Sự khác biệt giữa `exports` và `opens` rất quan trọng. `exports` công khai API; `opens` cho phép framework hoặc thư viện dùng reflection sâu, kể cả với thành viên private. Một package có thể được mở mà không được xuất.

### Strong encapsulation của các API nội bộ JDK

Từ JDK 17, các thành phần nội bộ của JDK được đóng gói mạnh mặc định. Mã ứng dụng không nên phụ thuộc vào lớp, phương thức hoặc trường nội bộ của JDK vì chúng không phải API ổn định. Tùy chọn `--illegal-access` đã lỗi thời và không còn nới lỏng quyền truy cập. `--add-opens` vẫn có thể mở một package cụ thể cho reflection trong tình huống tương thích, nhưng nên xem đây là biện pháp chuyển tiếp có phạm vi hẹp, không phải cấu hình mặc định của ứng dụng.

Khi cần reflection, API `AccessibleObject.trySetAccessible()` cho biết liệu quyền truy cập có thể được bật hay không. Phương thức trả về `false` khi module chứa lớp đích không mở package phù hợp cho module gọi. Cách này giúp xử lý trường hợp không được phép mà không cần dựa vào việc bỏ qua lỗi truy cập.

## 2. Cô lập mã không đáng tin cậy

Mã không đáng tin cậy có thể cố đọc hoặc sửa tệp, kết nối mạng, tạo tiến trình, kết thúc JVM, tiêu thụ CPU/bộ nhớ, tạo nhiều luồng hoặc khai thác thư viện mà tiến trình chủ có quyền sử dụng. Bài toán cô lập phải giới hạn những hành động và tài nguyên đó.

Các module trong cùng JVM vẫn chạy trong cùng tiến trình, cùng không gian bộ nhớ và cùng danh tính/quyền của tiến trình ở cấp hệ điều hành. Module không có user ID riêng, không có filesystem riêng, không có network namespace riêng và không có quota CPU/bộ nhớ độc lập. Một module có thể gọi các API công khai mà tiến trình được phép dùng. Vì vậy, việc không export package hoặc chặn reflection không ngăn được mã độc thực hiện các hành động hệ điều hành thông qua những API mà nó vẫn truy cập được.

Một thiết kế hiện đại thường thực hiện các bước sau:

1. **Chạy mã trong tiến trình riêng.** Dịch vụ chủ nhận yêu cầu, khởi chạy worker riêng và giao tiếp qua IPC có giao thức hẹp. Lỗi hoặc việc kết thúc worker không làm sập JVM chính.
2. **Giảm quyền của worker.** Dùng tài khoản hệ điều hành riêng, không có quyền quản trị, chỉ cấp quyền đọc/ghi đúng thư mục cần thiết. Không đưa credential, token, biến môi trường nhạy cảm, socket quản trị hoặc mount của máy chủ vào worker.
3. **Giới hạn tài nguyên.** Đặt giới hạn CPU, bộ nhớ, số tiến trình/luồng, dung lượng lưu trữ và thời gian chạy. Khi hết hạn, chấm dứt worker.
4. **Giới hạn truy cập hệ thống.** Tắt mạng nếu không cần; nếu cần thì chỉ cho phép đích cụ thể. Dùng filesystem chỉ đọc và thư mục tạm riêng. Có thể bổ sung seccomp, AppArmor hoặc SELinux tùy hệ điều hành.
5. **Dùng container hoặc máy ảo phù hợp với mức rủi ro.** Container được cấu hình chặt giúp cô lập filesystem, namespace và tài nguyên, nhưng vẫn dùng chung kernel với host. Với mã có khả năng đối kháng cao hoặc cần ranh giới mạnh hơn, cân nhắc VM/microVM hoặc dịch vụ sandbox chuyên dụng.
6. **Giữ IPC tối giản.** Chỉ gửi dữ liệu cần thiết; kiểm tra kiểu, kích thước và định dạng đầu vào/đầu ra. Đặt timeout, giới hạn kích thước kết quả và không tin dữ liệu trả về.

Chạy một tiến trình con dưới cùng tài khoản, với cùng quyền filesystem và network, chưa đủ để tạo sandbox. Ranh giới tiến trình chỉ có ý nghĩa khi quyền và tài nguyên của tiến trình đó được giới hạn ở cấp hệ điều hành.

## 3. Vì sao JPMS không phải sandbox

| Tiêu chí | Đóng gói mạnh JPMS | Cô lập mã không đáng tin cậy |
|---|---|---|
| Ranh giới chính | Module/package trong một JVM | Tiến trình và cơ chế bảo vệ của hệ điều hành hoặc máy ảo |
| Mục đích | Kiểm soát API, phụ thuộc và truy cập reflection | Hạn chế tác động lên host, dữ liệu và tài nguyên |
| Cơ chế | `requires`, `exports`, `opens`, quy tắc truy cập Java | Tài khoản riêng, quyền hệ điều hành, namespace, quota, container/VM |
| Phạm vi tài nguyên | Không tạo quota hoặc filesystem riêng cho module | Có thể giới hạn CPU, bộ nhớ, tiến trình, filesystem và network |
| Mã độc chạy cùng host | Vẫn có thể dùng API công khai mà tiến trình được phép dùng | Có thể bị giới hạn bởi quyền và ranh giới thực thi |

Một số nhầm lẫn cần tránh:

- **Không export package không đồng nghĩa với chặn mọi hành động.** Nó ngăn module khác truy cập kiểu trong package theo quy tắc JPMS; nó không thu hồi quyền đọc tệp hoặc kết nối mạng của cả tiến trình.
- **Không mở package không đồng nghĩa với vô hiệu hóa reflection hoàn toàn.** Quyền reflection còn phụ thuộc module, package và ngữ cảnh gọi. Mã trong cùng module có quyền khác với mã bên ngoài.
- **ClassLoader không phải ranh giới bảo mật.** ClassLoader hữu ích cho việc nạp lớp và quản lý namespace, nhưng không tạo danh tính hệ điều hành hoặc giới hạn tài nguyên độc lập.
- **`--add-opens` không tạo sandbox.** Tùy chọn này mở package cho reflection; dùng rộng rãi còn làm giảm hiệu quả đóng gói.
- **Không thiết kế sandbox mới dựa trên Security Manager.** Từ JDK 24, Security Manager đã bị vô hiệu hóa vĩnh viễn: JVM không cho bật ở lúc khởi động hoặc cài đặt một Security Manager tùy chỉnh lúc chạy. Các API liên quan đang được tiến tới loại bỏ.

## 4. Ví dụ: `exports` và `opens` có tác dụng khác nhau

Ví dụ có hai module. Module `com.example.secret` chỉ xuất package API, giữ lớp `Credential` trong package nội bộ và mở package đó cho đúng module consumer để minh họa deep reflection.

Cấu trúc thư mục:

```text
src/
├── com.example.secret/
│   ├── module-info.java
│   └── com/example/secret/
│       ├── api/CredentialFactory.java
│       └── internal/Credential.java
└── com.example.consumer/
    ├── module-info.java
    └── com/example/consumer/Main.java
```

**Module secret — module-info.java**

```java
module com.example.secret {
    exports com.example.secret.api;
    opens com.example.secret.internal to com.example.consumer;
}
```

**API được xuất — CredentialFactory.java**

```java
package com.example.secret.api;

import com.example.secret.internal.Credential;

public final class CredentialFactory {
    private CredentialFactory() {}

    public static Object create() {
        return new Credential("vault-key-123");
    }
}
```

**Kiểu nội bộ — Credential.java**

```java
package com.example.secret.internal;

public final class Credential {
    private final String value;

    public Credential(String value) {
        this.value = value;
    }
}
```

**Module consumer — module-info.java**

```java
module com.example.consumer {
    requires com.example.secret;
}
```

**Mã consumer — Main.java**

```java
package com.example.consumer;

import com.example.secret.api.CredentialFactory;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Object credential = CredentialFactory.create();
        Field valueField = credential.getClass().getDeclaredField("value");

        if (valueField.trySetAccessible()) {
            System.out.println(valueField.get(credential));
        } else {
            System.out.println("Deep reflection is not permitted");
        }
    }
}
```

Biên dịch từ thư mục chứa thư mục `src`:

```bash
javac --module-source-path src -d out -m com.example.secret,com.example.consumer
```

Chạy module consumer:

```bash
java --module-path out -m com.example.consumer/com.example.consumer.Main
```

Stdout khi có dòng `opens com.example.secret.internal to com.example.consumer;`:

```text
vault-key-123
```

Để kiểm tra giới hạn, xóa dòng `opens` khỏi `module-info.java` của `com.example.secret`, biên dịch lại vào thư mục output mới rồi chạy lại. Kết quả:

```text
Deep reflection is not permitted
```

Ví dụ cho thấy:

- Consumer biên dịch và gọi được `CredentialFactory` vì package API được `exports`.
- Package nội bộ không được `exports`, nên consumer không thể import và tham chiếu trực tiếp kiểu `Credential`.
- Khi package nội bộ được `opens` có giới hạn cho consumer, consumer có thể dùng reflection sâu ở thời điểm chạy.
- Bỏ `opens` khiến `trySetAccessible()` trả về `false`; API công khai vẫn hoạt động.

Đây chỉ là ví dụ về quyền truy cập module và reflection. Nó không chứng minh rằng consumer bị cô lập khỏi filesystem, network, CPU, bộ nhớ hoặc các API công khai khác của JVM.

## 5. Cách chọn cơ chế

- **Thiết kế thư viện hoặc ứng dụng modular:** dùng JPMS để khai báo phụ thuộc, xuất đúng API cần thiết và giữ package triển khai ở trạng thái đóng.
- **Framework cần truy cập private member:** chỉ mở package cần thiết cho đúng module framework; tránh mở toàn bộ module nếu không có yêu cầu cụ thể.
- **Tương thích với thư viện cũ cần reflection:** xác định package thực sự cần mở và dùng `--add-opens` có phạm vi hẹp trong thời gian chuyển đổi; ưu tiên cập nhật thư viện để bỏ phụ thuộc vào internals.
- **Chạy plugin do bên thứ ba cung cấp hoặc mã do người dùng gửi:** chạy trong worker riêng với tài khoản hệ điều hành ít quyền, giới hạn tài nguyên, filesystem và network; chọn container hoặc VM theo mức độ tin cậy.
- **Chạy mã đối kháng hoặc xử lý dữ liệu nhạy cảm:** ưu tiên sandbox/VM chuyên dụng, không chia sẻ secret hay quyền quản trị với tiến trình thực thi.

Có thể kết hợp JPMS với sandbox: JPMS giúp worker có API nội bộ gọn và rõ; sandbox cấp tiến trình giới hạn những gì worker có thể làm trên máy. Hai lớp này bổ sung cho nhau nhưng không thay thế nhau.

## 6. Kiểm tra nhanh trước khi triển khai

- [ ] Package nào là API công khai đã được liệt kê rõ trong `exports`?
- [ ] Package nào thực sự cần deep reflection và đã giới hạn bằng `opens ... to ...`?
- [ ] Có thể loại bỏ `open module` hoặc `--add-opens` diện rộng không?
- [ ] Mã không tin cậy có chạy trong tiến trình riêng không?
- [ ] Worker có tài khoản riêng, quyền filesystem/network tối thiểu và quota tài nguyên không?
- [ ] Worker có bị tách khỏi credential, socket quản trị và mount nhạy cảm của host không?
- [ ] IPC có giới hạn kích thước, kiểm tra dữ liệu và timeout không?
- [ ] Có cơ chế dừng worker và dọn tài nguyên khi hết thời gian hoặc phát hiện bất thường không?

## Tài liệu tham khảo

1. [Java Language Specification, Java SE 25 — Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html), đặc biệt §7.7 và §7.7.2 về module, package được export và package được open.
2. [Java SE 25 API — AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html), mô tả `trySetAccessible()`, `setAccessible()` và điều kiện mở package.
3. [Oracle Java SE 25 Security Developer's Guide — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html), xác nhận trạng thái từ JDK 24.
4. [Oracle — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html), phần Strong Encapsulation in the JDK về thay đổi từ JDK 17.
