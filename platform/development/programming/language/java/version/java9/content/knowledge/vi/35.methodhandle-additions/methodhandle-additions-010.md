# Giữ Lookup có quyền cao trong phạm vi tin cậy

## 1. Lookup là capability để tạo MethodHandle

`MethodHandles.Lookup` là đối tượng dùng để tạo `MethodHandle` hoặc `VarHandle` khi thao tác đó cần kiểm tra quyền truy cập. Lookup lưu danh tính của **lookup class** và các quyền mà lookup được phép sử dụng.

Cách tạo thông dụng:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

`MethodHandles.lookup()` là phương thức caller-sensitive: lookup class là class thực sự gọi phương thức này. Lookup trả về có đầy đủ quyền tương ứng với những thao tác bytecode mà class đó được phép thực hiện, bao gồm quyền truy cập private member của chính class và nestmate theo quy tắc Java.

Vì vậy, Lookup không chỉ là một đối tượng tiện ích. Nó là một **capability**: ai giữ được Lookup có quyền cao có thể yêu cầu nó tạo MethodHandle truy cập các thành viên mà lookup class ban đầu được phép truy cập.

Đây là lý do Javadoc của Java khuyến cáo chỉ delegate Lookup quyền cao cho thành phần đáng tin cậy và không lưu nó ở nơi mã không tin cậy có thể truy cập.

## 2. Quyền truy cập được kiểm tra lúc tạo handle

Khi gọi factory như:

~~~java
MethodHandle getter = lookup.findGetter(
        Account.class, "balance", long.class);
~~~

JVM kiểm tra quyền truy cập dựa trên lookup class và các lookup mode của đối tượng Lookup. Nếu thành viên tồn tại nhưng không được phép truy cập, thao tác tạo handle thất bại với `IllegalAccessException`. Nếu không tìm thấy thành viên, có thể nhận `NoSuchFieldException` hoặc `NoSuchMethodException`.

Một điểm bảo mật quan trọng: quyền truy cập được kiểm tra **khi tạo MethodHandle**, không được kiểm tra lại theo danh tính của từng caller mỗi lần handle được gọi. Khi một MethodHandle truy cập private member đã được tạo và đưa cho một thành phần khác, thành phần giữ handle có thể gọi đúng thao tác mà handle đại diện.

Do đó có hai loại capability cần bảo vệ:

- `Lookup` quyền cao: cho phép tạo nhiều handle trong phạm vi quyền của lookup class.
- `MethodHandle` nhạy cảm: cho phép thực hiện chính thao tác private mà handle đã đại diện.

Không nên nghĩ rằng giữ Lookup kín là đủ nếu ứng dụng lại chia sẻ một MethodHandle private cho mã không được phép sử dụng nó.

## 3. Xác định lookup class và lookup modes

Có thể kiểm tra ngữ cảnh và quyền hiện tại:

~~~java
Class<?> lookupClass = lookup.lookupClass();
int modes = lookup.lookupModes();

boolean canAccessPrivate =
        (modes & MethodHandles.Lookup.PRIVATE) != 0;
~~~

Trong Java 9, các lookup mode chính là:

| Mode | Ý nghĩa khái quát |
|---|---|
| `PUBLIC` | Truy cập public member theo quy tắc module |
| `PRIVATE` | Truy cập private member của lookup class và các nestmate được phép |
| `PROTECTED` | Truy cập protected member theo quy tắc package/subclass |
| `PACKAGE` | Truy cập member có package access |
| `MODULE` | Gắn quyền lookup với module nơi lookup ban đầu được tạo |
| `UNCONDITIONAL` | Public access không phụ thuộc readability như lookup thông thường |

`lookupModes()` trả về một bit mask. Hãy kiểm tra bit cần thiết bằng hằng số `Lookup.PRIVATE`, `Lookup.MODULE`... thay vì hard-code giá trị số.

`MethodHandles.lookup()` tạo lookup có đầy đủ quyền trong phạm vi caller. `MethodHandles.publicLookup()` tạo lookup có quyền tối thiểu: chỉ tạo handle cho public member của public class trong package được export vô điều kiện.

Trong các JDK mới hơn, tập mode có thể có thêm mode được bổ sung sau Java 9. Vì vậy, code nên kiểm tra từng capability cần dùng thay vì giả định toàn bộ bit mask luôn có một giá trị cố định.

## 4. Vì sao không chia sẻ Lookup quyền cao cho plugin hoặc mã không tin cậy?

Giả sử ứng dụng có class giữ dữ liệu riêng:

~~~java
private static String secret() {
    return "private data";
}
~~~

Nếu ứng dụng chuyển Lookup đầy đủ của class này cho một plugin, plugin có thể gọi:

~~~java
MethodHandle handle = lookup.findStatic(
        Host.class, "secret", MethodType.methodType(String.class));
~~~

Dù plugin không thể tự truy cập `Host.secret()` bằng cú pháp Java thông thường, nó có thể yêu cầu Lookup đã được cấp tạo handle cho private method đó. Plugin sau đó có thể gọi hoặc chuyển tiếp handle cho thành phần khác.

Việc chia sẻ Lookup vì thế tương đương với việc ủy quyền quyền tạo handle trong phạm vi quyền của lookup class. Không nên đưa Lookup quyền cao vào:

- API công khai cho plugin hoặc script do người dùng cung cấp.
- Registry, context hoặc service locator mà nhiều tenant có thể truy cập.
- Static field dùng chung giữa các thành phần khác mức tin cậy.
- Callback, event hoặc extension point không kiểm soát được người nhận.
- Cấu hình hay object graph được truyền ra khỏi vùng tin cậy.

Chỉ chia sẻ Lookup quyền cao khi bên nhận thực sự đáng tin cậy và cần quyền đó. Hãy xác định rõ ranh giới tin cậy trước khi delegate.

## 5. Dùng publicLookup khi chỉ cần API công khai

Nếu một thành phần chỉ cần gọi public API, hãy bắt đầu bằng:

~~~java
MethodHandles.Lookup lookup = MethodHandles.publicLookup();
~~~

Lookup này chỉ cho phép tạo handle tới public member của public class thuộc package được export vô điều kiện. Nó không cho phép truy cập private hoặc package-private member.

Đây là lựa chọn phù hợp khi framework cần tra cứu và cache các handle dùng chung cho API công khai. Nó giảm quyền ngay từ nguồn, giúp tránh vô tình cấp quyền private của một class nội bộ.

Nếu API cần public member trong một module/package chỉ export có điều kiện cho module gọi, hãy dùng lookup phù hợp với module caller thay vì giả định `publicLookup()` có thể truy cập mọi public class.

## 6. Thu hẹp quyền bằng dropLookupMode

Java 9 bổ sung:

~~~java
Lookup restricted = lookup.dropLookupMode(Lookup.PRIVATE);
~~~

Phương thức này trả về một Lookup mới trên cùng lookup class nhưng đã loại bỏ mode được yêu cầu. Đối tượng Lookup ban đầu không bị thay đổi; đối tượng mới không thể tự khôi phục các mode đã bị loại bỏ.

Một số quy tắc cần nhớ:

- Loại bỏ `PRIVATE` sẽ mất quyền private.
- Loại bỏ `PACKAGE` cũng loại bỏ `PRIVATE`.
- Loại bỏ `MODULE` cũng loại bỏ `PACKAGE` và `PRIVATE`.
- `PROTECTED` luôn bị loại bỏ trong Lookup sau khi gọi `dropLookupMode`.
- Loại bỏ `PUBLIC` làm Lookup không còn quyền truy cập.

Nếu mục tiêu là chỉ giữ public access từ một Lookup đầy đủ, có thể loại bỏ `MODULE`; thao tác này đồng thời bỏ PACKAGE và PRIVATE, còn PUBLIC được giữ lại:

~~~java
Lookup publicOnly = lookup.dropLookupMode(Lookup.MODULE);
~~~

Đừng chỉ loại bỏ `PRIVATE` rồi cho rằng Lookup đã trở thành public-only. Nó có thể vẫn giữ PACKAGE và các quyền khác.

## 7. Lookup.in không nâng quyền

`Lookup.in(Target.class)` tạo một Lookup có lookup class mới. Phương thức này không tăng quyền so với Lookup nguồn. Tùy quan hệ giữa class nguồn và class đích, các mode có thể bị loại bỏ khi khác package, nest hoặc module.

~~~java
Lookup targetContext = lookup.in(Target.class);
~~~

Hãy xem `in` là phép chuyển ngữ cảnh có thể làm giảm quyền, không phải cách lấy quyền của class đích. Nếu cần cấp quyền private cho target, đó là trường hợp riêng của `privateLookupIn` và vẫn chịu các điều kiện module.

## 8. privateLookupIn và ranh giới module

Java 9 bổ sung:

~~~java
Lookup targetLookup =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

Phương thức này tạo Lookup có private access trên class đích nếu caller lookup đáp ứng điều kiện truy cập sâu (deep reflection).

Với JDK hiện hành, caller Lookup cần full-privilege access, gồm `PRIVATE` và `MODULE`. Khi target class ở module khác, còn cần:

1. Module của caller đọc được module của target (`requires` hoặc quan hệ readability tương ứng).
2. Package chứa target class được mở cho module caller bằng `opens`.

Nếu target ở cùng module với caller, không cần mở package qua ranh giới module. Nếu target ở module khác, Lookup kết quả có private access tới target nhưng mất `MODULE` access; nó không thể tiếp tục được dùng để mở một chuỗi private lookup tùy ý sang module thứ ba.

### exports khác opens

- `exports` cho phép module khác truy cập các public type/member theo quy tắc Java.
- `opens` cho phép deep reflection vào package, bao gồm các thao tác cần quyền private thông qua cơ chế như `privateLookupIn`.

Ví dụ module descriptor:

~~~java
// module-info.java của app.module
module app.module {
    requires target.module;
}
~~~

~~~java
// module-info.java của target.module
module target.module {
    opens com.example.internal to app.module;
}
~~~

Package chỉ mở cho `app.module`, thay vì mở rộng cho tất cả module. Chỉ mở package khi có nhu cầu thực tế và đã xác định module nhận quyền là đáng tin cậy.

`privateLookupIn` không phải đường tắt để bỏ qua module encapsulation. Nếu caller không đọc target module, package không được mở, hoặc Lookup caller thiếu quyền cần thiết, thao tác sẽ thất bại với `IllegalAccessException`.

## 9. Ví dụ Java chạy được: rò rỉ Lookup và thu hẹp quyền

Ví dụ dưới đây mô phỏng một plugin không tin cậy nhận Lookup quyền cao. Plugin tạo được MethodHandle cho private method của host. Sau đó host tạo Lookup mới chỉ giữ public access và chứng minh lookup đã thu hẹp không còn tạo được private handle.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;
import java.lang.invoke.MethodType;

public class LookupTrustBoundaryDemo {
    private static String secret() {
        return "private data";
    }

    public static String publicInfo() {
        return "public data";
    }

    private static final class Target {
        private static String hidden() {
            return "target private data";
        }
    }

    private static boolean hasMode(Lookup lookup, int mode) {
        return (lookup.lookupModes() & mode) != 0;
    }

    public static void main(String[] args) throws Throwable {
        Lookup privileged = MethodHandles.lookup();
        System.out.println("lookup class = "
                + privileged.lookupClass().getSimpleName());
        System.out.println("has private access = "
                + hasMode(privileged, Lookup.PRIVATE));

        MethodHandle delegated =
                UntrustedPlugin.createPrivateHandle(privileged);
        System.out.println("private handle result = "
                + (String) delegated.invokeExact());

        Lookup narrowed = privileged.dropLookupMode(Lookup.MODULE);
        System.out.println("narrowed has private access = "
                + hasMode(narrowed, Lookup.PRIVATE));
        System.out.println("public via narrowed lookup = "
                + (String) narrowed.findStatic(
                        LookupTrustBoundaryDemo.class,
                        "publicInfo", MethodType.methodType(String.class))
                        .invokeExact());
        try {
            narrowed.findStatic(LookupTrustBoundaryDemo.class,
                    "secret", MethodType.methodType(String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("private via narrowed lookup = denied");
        }

        Lookup publicOnly = MethodHandles.publicLookup();
        System.out.println("publicLookup can find public = "
                + (String) publicOnly.findStatic(
                        LookupTrustBoundaryDemo.class,
                        "publicInfo", MethodType.methodType(String.class))
                        .invokeExact());
        try {
            publicOnly.findStatic(LookupTrustBoundaryDemo.class,
                    "secret", MethodType.methodType(String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("private via publicLookup = denied");
        }

        Lookup targetLookup =
                MethodHandles.privateLookupIn(Target.class, privileged);
        MethodHandle targetPrivate = targetLookup.findStatic(
                Target.class, "hidden", MethodType.methodType(String.class));
        System.out.println("privateLookupIn result = "
                + (String) targetPrivate.invokeExact());
        System.out.println("target lookup class = "
                + targetLookup.lookupClass().getSimpleName());
    }
}

final class UntrustedPlugin {
    static MethodHandle createPrivateHandle(Lookup delegatedLookup)
            throws NoSuchMethodException, IllegalAccessException {
        return delegatedLookup.findStatic(
                LookupTrustBoundaryDemo.class,
                "secret", MethodType.methodType(String.class));
    }
}
~~~

Lưu mã nguồn trong `LookupTrustBoundaryDemo.java`, biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all LookupTrustBoundaryDemo.java
java LookupTrustBoundaryDemo
~~~

Kết quả:

~~~text
lookup class = LookupTrustBoundaryDemo
has private access = true
private handle result = private data
narrowed has private access = false
public via narrowed lookup = public data
private via narrowed lookup = denied
publicLookup can find public = public data
private via publicLookup = denied
privateLookupIn result = target private data
target lookup class = Target
~~~

Ví dụ cũng tương thích với Java 9 và có thể biên dịch bằng:

~~~bash
javac --release 9 -Xlint:all LookupTrustBoundaryDemo.java
java LookupTrustBoundaryDemo
~~~

Kết quả cho thấy plugin không tự có quyền private của host, nhưng có thể tạo private MethodHandle khi được cấp Lookup quyền cao. Sau khi host tạo Lookup mới bằng `dropLookupMode(MODULE)`, handle private không còn tạo được, trong khi public API vẫn truy cập được.

Phần `privateLookupIn` trong ví dụ dùng target cùng module để minh họa việc tạo lookup cho class đích. Truy cập target ở module khác còn phải đáp ứng readability và `opens` như phần trước. Ví dụ đã được biên dịch và chạy với cả `javac --release 9 -Xlint:all` và `javac --release 17 -Xlint:all`; stdout khớp với kết quả trên.

## 10. Các lỗi thiết kế thường gặp

- **Trả Lookup đầy đủ từ getter công khai:** caller có thể tạo handle cho private member trong phạm vi lookup class.
- **Đưa Lookup vào plugin context dùng chung:** mọi plugin có thể nhận cùng capability dù chỉ một plugin cần quyền đó.
- **Chỉ bảo vệ Lookup mà chia sẻ private MethodHandle:** handle đã tạo vẫn cho phép gọi member được ủy quyền.
- **Dùng `dropLookupMode(PRIVATE)` rồi coi là public-only:** PACKAGE có thể vẫn còn; hãy xác định chính xác các mode còn lại.
- **Dùng `Lookup.in` để mong tăng quyền:** phương thức này không bao giờ cấp thêm quyền.
- **Dùng `privateLookupIn` để bỏ qua module:** caller vẫn phải có quyền phù hợp và package đích phải được mở khi qua module.
- **Nhầm `exports` với `opens`:** export public API không tự cho phép deep reflection vào private member.
- **Hard-code lookup mode mask:** dùng các hằng số và kiểm tra từng bit vì các JDK có thể bổ sung mode.
- **Dựa vào tên hoặc `toString()` để quyết định quyền:** kiểm tra bằng `lookupClass()` và `lookupModes()` trong code cần kiểm soát.

## 11. Checklist trước khi delegate Lookup

1. Bên nhận có thực sự thuộc vùng tin cậy không?
2. Bên nhận cần tạo handle hay chỉ cần gọi một thao tác cụ thể?
3. Có thể dùng `publicLookup()` thay Lookup đầy đủ không?
4. Nếu cần Lookup dẫn xuất, đã thu hẹp bằng `dropLookupMode` và xác minh các mode còn lại chưa?
5. Có vô tình chia sẻ MethodHandle private hoặc VarHandle nhạy cảm sau khi tạo không?
6. Nếu dùng `privateLookupIn`, caller có đủ quyền và module target đã mở đúng package cho caller chưa?
7. Module chỉ mở package cho đúng module đáng tin cậy chưa?
8. Có test xác nhận lookup bị thu hẹp không thể tạo các handle ngoài quyền dự kiến không?

Hãy giữ Lookup có quyền cao trong code đáng tin cậy, tạo handle ở đúng ranh giới, và chỉ chuyển tiếp capability nhỏ nhất mà thành phần nhận cần dùng.

## 12. Tài liệu tham khảo

- [MethodHandles.Lookup — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.Lookup.html)
- [MethodHandles — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.html)
- [MethodHandles.Lookup — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [MethodHandles — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html)