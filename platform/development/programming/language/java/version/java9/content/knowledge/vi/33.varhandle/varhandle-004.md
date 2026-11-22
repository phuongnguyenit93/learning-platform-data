# Kiểm tra quyền khi tạo handle bằng VarHandle

`VarHandle` là một tham chiếu có kiểu đến một biến hoặc một vị trí phần tử, cho phép đọc, ghi và thực hiện các thao tác nguyên tử với nhiều mức thứ tự bộ nhớ. Khi tạo handle cho field của một class, Java phải xác định code đang yêu cầu có quyền truy cập field đó hay không. Quyền này được kiểm tra dựa trên `MethodHandles.Lookup` được dùng để tìm field.

Điểm quan trọng là **quyền truy cập thành viên được kiểm tra khi tạo VarHandle**. Sau khi một handle đã được tạo thành công, code giữ handle có thể gọi các access mode mà handle hỗ trợ mà không phải thực hiện lại kiểm tra visibility của field ở mỗi lần gọi. Vì vậy, một VarHandle trỏ đến field private là một capability: chỉ truyền handle đó cho code đáng tin cậy.

## 1. Lookup là nguồn quyền truy cập

Các factory method tìm field nằm trên `MethodHandles.Lookup`:

- `MethodHandles.lookup()` tạo Lookup mang quyền của class nơi lời gọi được thực hiện. Đây là lựa chọn thông thường khi class muốn tạo handle cho các thành viên của chính nó.
- `MethodHandles.publicLookup()` chỉ có quyền public, dùng cho public class và public member trong package được module export phù hợp.
- `MethodHandles.privateLookupIn(targetClass, callerLookup)` tạo một Lookup có private access đối với target class nếu caller đáp ứng các điều kiện truy cập của Java Platform Module System.
- `lookup.in(targetClass)` chuyển ngữ cảnh lookup sang class khác nhưng không tự nâng quyền. Một Lookup không thể dùng `in` để tự cấp private access mà nó vốn không có.

Lookup gắn với một lookup class và một tập lookup mode. Nó không phải đối tượng đại diện cho quyền truy cập toàn JVM. Quyền mà nó có được xác định tại nơi Lookup được tạo và có thể bị thu hẹp khi chuyển đổi.

Ví dụ, nếu `Main` gọi `MethodHandles.lookup()` thì lookup class là `Main`. Việc `Main` nằm cùng package với `Account` có thể cho phép truy cập package-private, nhưng không tự động cấp quyền truy cập field private của một top-level class khác.

## 2. findVarHandle và findStaticVarHandle

Dùng đúng factory theo loại field:

```java
VarHandle instanceHandle = lookup.findVarHandle(
        Account.class,
        "balance",
        int.class
);

VarHandle staticHandle = lookup.findStaticVarHandle(
        Account.class,
        "nextId",
        int.class
);
```

`findVarHandle` tìm field instance. Khi gọi access mode, phải truyền receiver trước:

```java
int value = (int) instanceHandle.get(account);
instanceHandle.set(account, 125);
```

`findStaticVarHandle` tìm field static. Không cần truyền receiver:

```java
int next = (int) staticHandle.get();
staticHandle.set(2);
```

Tên field và kiểu field phải khớp chính xác. `int.class` không tương đương `Integer.class`, và một kiểu số khác như `long.class` cũng không được tự chuyển đổi. Nếu không tìm thấy field phù hợp với tên và kiểu đã khai báo, factory method có thể ném `NoSuchFieldException`.

Cũng phải dùng đúng loại field. `findVarHandle` dành cho instance field; `findStaticVarHandle` dành cho static field. Yêu cầu sai loại sẽ không tạo được handle và có thể dẫn đến `IllegalAccessException`.

## 3. Quyền được kiểm tra tại thời điểm tạo handle

Khi gọi `findVarHandle` hoặc `findStaticVarHandle`, Lookup kiểm tra class, package, member visibility và các quy tắc truy cập module có liên quan. Nếu caller không có quyền, method ném `IllegalAccessException`.

Ví dụ, `publicLookup()` có thể tạo handle cho field public của một class public nằm trong package được export. Cùng Lookup đó không thể tạo handle cho field private.

Nếu một handle private đã được tạo thành công bằng Lookup có đủ quyền, code nhận handle có thể dùng các access mode được hỗ trợ. Nó không cần tự có quyền private đối với class chứa field. Đây là lý do handle nên được xem như một capability và không nên chia sẻ tùy tiện.

Điều này không có nghĩa mọi lời gọi access mode đều chắc chắn thành công. Khi sử dụng handle, JVM vẫn kiểm tra các điều kiện vận hành như receiver có đúng kiểu, coordinate có hợp lệ, kiểu giá trị có khớp và access mode có được hỗ trợ hay không. Kiểm tra visibility của field và kiểm tra tính hợp lệ của từng lần truy cập là hai việc khác nhau.

## 4. Truy cập private field bằng privateLookupIn

Nếu một class khác cần truy cập private field, `privateLookupIn` là API phù hợp khi quyền module cho phép:

```java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Account.class,
                MethodHandles.lookup()
        );

VarHandle balanceHandle = privateLookup.findVarHandle(
        Account.class,
        "balance",
        int.class
);
```

Caller Lookup phải có các lookup mode cần thiết, bao gồm private và module access. Khi target class nằm trong module khác, module của caller phải đọc được module đích và package chứa target class phải được mở cho module caller.

Trong một ứng dụng không dùng named module (unnamed module), việc kiểm tra module thường đơn giản hơn. Khi triển khai với named module, cần khai báo rõ quan hệ module.

Ví dụ cấu trúc module:

```java
// module-info.java của module app
module app {
    requires model;
}
```

```java
// module-info.java của module model
module model {
    exports com.example.model to app;
    opens com.example.model to app;
}
```

Ở đây:

- `requires model` tạo quan hệ readability để module `app` đọc module `model`.
- `exports com.example.model to app` cho phép code trong `app` truy cập các kiểu và thành viên public được export trong package.
- `opens com.example.model to app` cho phép các API truy cập sâu như `privateLookupIn` thực hiện truy cập private trong package đó, nếu các điều kiện Lookup còn lại được đáp ứng.

`exports` và `opens` không thay thế cho nhau. Export package cho phép truy cập public theo quy tắc module; open package cho phép truy cập sâu hơn. Không nên mở toàn bộ module hoặc package rộng hơn nhu cầu thực tế.

Nếu package không được mở cho caller module, `privateLookupIn` qua ranh giới module sẽ thất bại với `IllegalAccessException`. Có thể giải quyết bằng cách điều chỉnh module descriptor của module sở hữu class, nếu thiết kế và quyền triển khai cho phép; không nên tìm cách lách quy tắc module.

## 5. Ví dụ đầy đủ: public lookup, private lookup và static field

Ví dụ dùng hai file để bảo đảm `Main` và `Account` là hai top-level class riêng biệt. Điều này giúp minh họa rõ việc lookup của `Main` không tự có private access đến field của `Account`.

**Account.java**

```java
public class Account {
    private int balance = 100;
    public int id = 7;
    private static int nextId = 1;
    private final int code = 9;
}
```

**Main.java**

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account();
        MethodHandles.Lookup callerLookup = MethodHandles.lookup();

        try {
            callerLookup.findVarHandle(
                    Account.class, "balance", int.class);
            throw new AssertionError("Unexpected private-field access");
        } catch (IllegalAccessException expected) {
            System.out.println("Ordinary lookup denied: "
                    + expected.getClass().getSimpleName());
        }

        VarHandle publicId = MethodHandles.publicLookup()
                .findVarHandle(Account.class, "id", int.class);
        System.out.println("Public lookup read id: " + publicId.get(account));

        MethodHandles.Lookup accountLookup =
                MethodHandles.privateLookupIn(Account.class, callerLookup);

        VarHandle balance = accountLookup.findVarHandle(
                Account.class, "balance", int.class);

        System.out.println("Private lookup read balance: "
                + balance.get(account));
        balance.set(account, 125);
        System.out.println("Balance after set: " + balance.get(account));
        System.out.println("SET supported: "
                + balance.isAccessModeSupported(VarHandle.AccessMode.SET));

        VarHandle nextId = accountLookup.findStaticVarHandle(
                Account.class, "nextId", int.class);
        System.out.println("Static field before update: " + nextId.get());
        nextId.set(2);
        System.out.println("Static field after update: " + nextId.get());

        try {
            accountLookup.findVarHandle(
                    Account.class, "balance", long.class);
            throw new AssertionError("Unexpected field type match");
        } catch (NoSuchFieldException expected) {
            System.out.println("Wrong field type denied: "
                    + expected.getClass().getSimpleName());
        }

        VarHandle code = accountLookup.findVarHandle(
                Account.class, "code", int.class);
        System.out.println("Final field read: " + code.get(account));
        System.out.println("Final field SET supported: "
                + code.isAccessModeSupported(VarHandle.AccessMode.SET));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Account.java Main.java
java Main
```

Kết quả stdout:

```text
Ordinary lookup denied: IllegalAccessException
Public lookup read id: 7
Private lookup read balance: 100
Balance after set: 125
SET supported: true
Static field before update: 1
Static field after update: 2
Wrong field type denied: NoSuchFieldException
Final field read: 9
Final field SET supported: false
```

Ví dụ thể hiện các trường hợp:

1. Lookup thông thường của `Main` không truy cập được field private `balance` của top-level class `Account`.
2. Public lookup tạo được handle cho field public `id`.
3. `privateLookupIn` tạo Lookup có private access đến `Account`; handle đọc và ghi được `balance`.
4. Field static `nextId` được tìm bằng `findStaticVarHandle` và được truy cập mà không cần receiver.
5. Kiểu field sai không được tự ép kiểu; tên và kiểu phải khớp.
6. Field final vẫn có thể được đọc, nhưng access mode `SET` không được hỗ trợ.

## 6. Kiểm tra access mode sau khi có handle

Quyền truy cập field không đồng nghĩa mọi thao tác đều được phép. Mỗi VarHandle hỗ trợ một tập access mode tùy loại biến và đặc tính của biến đó.

Các mode thường gặp:

| Access mode | Ý nghĩa |
|---|---|
| `GET` / `SET` | Đọc hoặc ghi theo plain memory semantics |
| `GET_VOLATILE` / `SET_VOLATILE` | Đọc hoặc ghi với volatile memory semantics |
| `GET_ACQUIRE` / `SET_RELEASE` | Đọc acquire hoặc ghi release |
| `COMPARE_AND_SET` | So sánh và cập nhật nguyên tử nếu giá trị hiện tại khớp |
| `COMPARE_AND_EXCHANGE` | Trả giá trị quan sát được và thử cập nhật nguyên tử |
| `GET_AND_SET` / `GET_AND_ADD` | Cập nhật nguyên tử và trả giá trị trước đó |

Dùng `isAccessModeSupported(mode)` để kiểm tra mode trước khi chọn thao tác động. Ví dụ:

```java
if (handle.isAccessModeSupported(VarHandle.AccessMode.COMPARE_AND_SET)) {
    boolean changed = handle.compareAndSet(receiver, expected, update);
}
```

Một field final chỉ hỗ trợ các thao tác đọc; các mode ghi và cập nhật không được hỗ trợ. Các kiểu biến khác nhau cũng có thể không hỗ trợ mọi mode, ví dụ phép cộng nguyên tử chỉ phù hợp với kiểu số được API hỗ trợ.

Memory ordering và quyền truy cập là hai trục độc lập. `GET_VOLATILE` không cấp thêm quyền private; nó chỉ chọn semantics bộ nhớ cho lần đọc trên một handle đã được tạo hợp lệ.

## 7. Lỗi thường gặp và cách xử lý

| Tình huống | Kết quả hoặc nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng public lookup cho private field | `IllegalAccessException` | Dùng Lookup có quyền phù hợp hoặc thiết kế API public thay thế |
| Dùng `lookup.in` để mong có private access | Lookup không được nâng quyền | Dùng `privateLookupIn` nếu điều kiện truy cập cho phép |
| Module đích không mở package | `privateLookupIn` bị từ chối | Kiểm tra readability và khai báo `opens` có phạm vi hẹp |
| Dùng findVarHandle với tên hoặc kiểu sai | `NoSuchFieldException` | Kiểm tra chính xác tên field và kiểu khai báo |
| Dùng findVarHandle cho static field | Sai loại factory | Dùng `findStaticVarHandle` |
| Dùng findStaticVarHandle cho instance field | Sai loại factory | Dùng `findVarHandle` |
| Gọi access mode không được hỗ trợ | `UnsupportedOperationException` | Kiểm tra `isAccessModeSupported` |
| Truyền receiver hoặc giá trị sai kiểu | Kiểm tra kiểu tại lần truy cập thất bại | Dùng đúng receiver và kiểu coordinate/value |

Không nên dùng một Lookup có quyền cao hơn phạm vi cần thiết chỉ để tránh thiết kế API. Nếu nhiều thành phần cần thay đổi balance, cân nhắc cung cấp phương thức nghiệp vụ như `deposit` hoặc `withdraw` thay vì chia sẻ handle private trực tiếp.

## 8. Quy tắc thiết kế an toàn

- Tạo Lookup ở class có trách nhiệm sở hữu thao tác truy cập.
- Chỉ dùng `privateLookupIn` khi có nhu cầu rõ ràng và module đích cho phép.
- Không chia sẻ VarHandle private cho code không đáng tin cậy; người nhận handle có thể sử dụng các access mode mà handle hỗ trợ.
- Không nhầm việc tạo được handle với việc mọi access mode đều được hỗ trợ.
- Kiểm tra chính xác tên, kiểu và static/instance của field.
- Dùng `isAccessModeSupported` khi access mode phụ thuộc runtime.
- Giữ package trong module ở trạng thái đóng mặc định; chỉ mở package cụ thể cho module cần quyền sâu.
- Nếu không cần thao tác ở mức field, ưu tiên API nghiệp vụ công khai để giữ invariant và quyền sở hữu dữ liệu.

VarHandle cho phép thao tác trực tiếp trên biến với semantics bộ nhớ rõ ràng, nhưng quyền truy cập phải được cấp có chủ đích. `MethodHandles.Lookup` quyết định code có thể tạo handle cho field nào; `privateLookupIn` chỉ cấp private access khi quy tắc module cho phép; còn access mode quyết định loại thao tác mà handle hỗ trợ. Nắm rõ ba lớp này giúp tránh `IllegalAccessException`, cấu hình module sai và vô tình phát tán capability truy cập private.
