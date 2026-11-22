# Điều chỉnh quyền Lookup bằng dropLookupMode trong Java

## 1. Lookup là một capability

MethodHandles.Lookup là đối tượng đại diện cho quyền mà một class có khi tìm kiếm field, method, constructor hoặc tạo MethodHandle. Quyền này được giới hạn bởi lookup class và tập lookup modes mà đối tượng đang giữ.

Tạo Lookup gắn với class hiện tại:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

Lookup được tạo từ lookup() có quyền theo ngữ cảnh của class gọi phương thức, tuân theo quy tắc truy cập của Java và hệ thống module. Nó có thể tạo handle cho thành viên private của chính lookup class và những thành viên khác mà class đó được phép truy cập.

Một Lookup có thể được truyền cho code khác. Người nhận có thể dùng nó để tạo MethodHandle trong phạm vi quyền mà Lookup cho phép. Vì vậy, hãy xem Lookup như một capability: ai giữ nó có thể sử dụng những quyền tra cứu mà nó mang theo.

## 2. Các lookup mode trong Java 9

lookupModes() trả về một bit mask mô tả các quyền của Lookup. Các mode có từ Java 9 gồm:

| Mode | Bit mask | Quyền |
|---|---:|---|
| PUBLIC | 0x01 | Truy cập public member của kiểu có thể truy cập |
| PRIVATE | 0x02 | Truy cập private member của lookup class |
| PROTECTED | 0x04 | Truy cập protected member theo quy tắc package và inheritance |
| PACKAGE | 0x08 | Truy cập member có package access trong runtime package |
| MODULE | 0x10 | Truy cập public type trong module của lookup class và package được export phù hợp |
| UNCONDITIONAL | 0x20 | Quyền public đặc biệt của publicLookup, giả định module readability |

Các giá trị là bit mask và có thể kết hợp. Lookup đầy đủ được tạo trong class gọi lookup() thường có PUBLIC, PRIVATE, PROTECTED, PACKAGE và MODULE; nó không có UNCONDITIONAL.

Ví dụ kiểm tra:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
int modes = lookup.lookupModes();

boolean canPrivate =
    (modes & MethodHandles.Lookup.PRIVATE) != 0;
boolean canPackage =
    (modes & MethodHandles.Lookup.PACKAGE) != 0;
~~~

lookupModes() cho biết quyền của Lookup tại thời điểm kiểm tra. Đây không phải cam kết rằng mọi member đều truy cập được: visibility, lookup class, runtime package và module exports vẫn được kiểm tra khi tạo handle.

## 3. dropLookupMode làm gì?

dropLookupMode(modeToDrop) tạo một Lookup mới trên cùng lookup class nhưng đã loại bỏ mode được chỉ định:

~~~java
MethodHandles.Lookup reduced =
    lookup.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Các đặc điểm quan trọng:

- Lookup mới vẫn có cùng lookupClass().
- Lookup mới có ít quyền hơn hoặc bằng Lookup ban đầu.
- Lookup ban đầu không bị thay đổi.
- Quyền đã loại bỏ không thể được khôi phục bằng cách tiếp tục biến đổi Lookup đã giảm quyền.
- Nếu không có thay đổi nào cần thực hiện, API có thể trả về chính Lookup hiện tại.

Mục tiêu của API là giới hạn khả năng tạo MethodHandle khi chia sẻ Lookup cho code khác. Ví dụ, một component có thể cần truy cập member trong package nhưng không được phép truy cập private member. Ta tạo Lookup đã bỏ PRIVATE rồi chỉ truyền bản đã giảm quyền đó.

## 4. Quy tắc phụ thuộc giữa các mode

Các mode có quan hệ phụ thuộc. dropLookupMode không chỉ xóa một bit độc lập trong mọi trường hợp.

| Mode bị bỏ | Những quyền bị loại bỏ |
|---|---|
| PRIVATE | PRIVATE; PROTECTED và UNCONDITIONAL cũng luôn bị loại bỏ |
| PROTECTED | PROTECTED và UNCONDITIONAL |
| PACKAGE | PACKAGE, PRIVATE, PROTECTED và UNCONDITIONAL |
| MODULE | MODULE, PACKAGE, PRIVATE, PROTECTED và UNCONDITIONAL |
| PUBLIC | Tất cả quyền truy cập |
| UNCONDITIONAL | Với publicLookup, Lookup không còn quyền truy cập |

PROTECTED và UNCONDITIONAL luôn bị loại khỏi Lookup thông thường sau khi gọi dropLookupMode. Các quy tắc này ngăn Lookup giữ một quyền cao hơn khi quyền nền tảng cần thiết đã bị bỏ.

Bỏ PACKAGE cũng bỏ PRIVATE vì private access phụ thuộc vào package access. Bỏ MODULE làm mất PACKAGE và PRIVATE vì Lookup không còn quyền truy cập module cần thiết để hỗ trợ các quyền đó.

## 5. Bỏ PRIVATE: giữ package access nhưng không còn private access

Khi cần chia sẻ Lookup cho code khác trong cùng package nhưng không muốn cấp quyền private:

~~~java
MethodHandles.Lookup packageLookup =
    MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Với Lookup đầy đủ trong một class thông thường, bản giảm quyền này vẫn giữ PUBLIC, PACKAGE và MODULE. PRIVATE bị bỏ; PROTECTED và UNCONDITIONAL cũng bị loại theo quy tắc của API.

Delegate vẫn có thể tạo handle cho thành viên package-access trong phạm vi runtime package mà Lookup được phép, nhưng không thể tạo handle cho private member.

Ví dụ sau chỉ thành công nếu packageValue có package access và thực sự nằm trong runtime package được phép:

~~~java
MethodHandles.Lookup reduced =
    MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);

MethodHandle getter = reduced.findGetter(
    SomeClass.class,
    "packageValue",
    int.class
);
~~~

Việc bỏ PRIVATE không mở package khác và không vượt qua module boundary.

## 6. Bỏ PACKAGE: giữ quyền MODULE nhưng không còn package/private

Nếu chỉ muốn delegate quyền truy cập public type trong module, bỏ PACKAGE:

~~~java
MethodHandles.Lookup moduleLookup =
    MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PACKAGE);
~~~

Lookup này giữ PUBLIC và MODULE, nhưng mất PACKAGE và PRIVATE. Nó có thể tạo handle cho public member trong phạm vi module access cho phép, nhưng không thể truy cập package-private hoặc private member.

Đây là cách hữu ích khi một thành phần chỉ cần làm việc với API public của module. Quyền module không đồng nghĩa với quyền truy cập mọi package-private member trong module.

## 7. Bỏ MODULE: chỉ còn public access

Khi muốn giới hạn Lookup ở public access:

~~~java
MethodHandles.Lookup publicOnly =
    MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.MODULE);
~~~

Bỏ MODULE cũng loại PACKAGE và PRIVATE. PROTECTED và UNCONDITIONAL luôn bị loại. PUBLIC vẫn còn.

Lookup này chỉ tạo được handle cho public member của public type mà lookup class có thể truy cập theo quy tắc readability và exports của module.

Đây là cách giảm quyền phù hợp khi chia sẻ Lookup cho thành phần chỉ cần API public. Nó không hoàn toàn giống publicLookup(): publicLookup có UNCONDITIONAL mode đặc biệt, trong khi Lookup vừa bỏ MODULE vẫn giữ PUBLIC gắn với lookup class và các quy tắc module của nó.

## 8. Bỏ PUBLIC: Lookup không còn quyền truy cập

PUBLIC là nền tảng cho member access. Nếu bỏ PUBLIC, Lookup mới không còn quyền truy cập:

~~~java
MethodHandles.Lookup noAccess =
    MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PUBLIC);
~~~

noAccess.lookupModes() trả về 0 trong trường hợp Lookup thông thường. Những lần tìm kiếm member tiếp theo sẽ thất bại vì không còn quyền truy cập.

Thao tác này không xóa Lookup ban đầu và cũng không thu hồi các MethodHandle đã được tạo từ trước.

## 9. publicLookup và UNCONDITIONAL

MethodHandles.publicLookup() tạo một Lookup dành cho public access. Nó dùng UNCONDITIONAL mode đặc biệt, cho phép truy cập public type trong package được export vô điều kiện mà không cần dựa vào readability của module chứa lookup class.

~~~java
MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();
~~~

Nếu bỏ UNCONDITIONAL khỏi publicLookup, Lookup kết quả không còn quyền truy cập:

~~~java
MethodHandles.Lookup noAccess =
    MethodHandles.publicLookup().dropLookupMode(
        MethodHandles.Lookup.UNCONDITIONAL
    );
~~~

Không nhầm UNCONDITIONAL với PUBLIC của Lookup thông thường. Hai mode có quy tắc kiểm tra module khác nhau.

UNCONDITIONAL là mode đã có trong Java 9. Bài này chỉ dùng các mode Java 9, không phụ thuộc những mode được bổ sung ở phiên bản Java mới hơn.

## 10. dropLookupMode khác Lookup.in như thế nào?

Cả dropLookupMode và in đều có thể tạo Lookup với ít quyền hơn, nhưng mục đích khác nhau.

| API | Lookup class | Tác động chính |
|---|---|---|
| dropLookupMode(mode) | Giữ nguyên | Loại một mode và các quyền phụ thuộc |
| in(newClass) | Đổi sang class mới | Giảm quyền theo quan hệ package, nest, module và khả năng truy cập class |

dropLookupMode phù hợp khi muốn giữ nguyên lookup class nhưng giảm capability được chia sẻ.

in phù hợp khi muốn chuyển ngữ cảnh tra cứu sang class khác. Khi class mới ở package, nest hoặc module khác, một số quyền có thể bị mất. in không cấp thêm quyền so với Lookup ban đầu.

Cả hai thao tác đều không thể nâng quyền vượt quá quyền mà Lookup ban đầu sở hữu.

## 11. dropLookupMode khác privateLookupIn như thế nào?

privateLookupIn tạo Lookup cho một class đích với private access nếu các điều kiện truy cập được đáp ứng. dropLookupMode giảm quyền của Lookup hiện tại.

- privateLookupIn chuyển ngữ cảnh tra cứu sang class đích và có thể tạo quyền private trong điều kiện module hợp lệ.
- dropLookupMode chỉ giảm quyền trên cùng lookup class.
- Lookup đã bị giảm quyền không thể dùng dropLookupMode để lấy lại quyền.
- privateLookupIn yêu cầu Lookup ban đầu có quyền thích hợp và package đích phải mở khi đi qua module khác.

Không dùng privateLookupIn để thay thế dropLookupMode khi mục tiêu là giới hạn quyền trước khi delegate. Hai API giải quyết hai vấn đề khác nhau.

## 12. Lookup là capability: giảm quyền trước khi chia sẻ

Một Lookup đầy đủ có thể tạo handle cho private member mà class gọi được phép truy cập. Nếu đưa Lookup đó cho plugin hoặc component không hoàn toàn tin cậy, component có thể tạo thêm handle trong phạm vi quyền đó.

Thay vì truyền Lookup đầy đủ, tạo một bản đã giảm quyền:

~~~java
MethodHandles.Lookup trusted = MethodHandles.lookup();

MethodHandles.Lookup publicOnly =
    trusted.dropLookupMode(MethodHandles.Lookup.MODULE);

plugin.initialize(publicOnly);
~~~

Đây là ví dụ minh họa nguyên tắc. Trong ứng dụng thực tế, hãy cấp đúng mức quyền plugin cần và kiểm tra thêm quyền truy cập class/member cùng module exports.

Có thể chọn mức quyền:

- PRIVATE bị bỏ: delegate không thể tra cứu private member.
- PACKAGE bị bỏ: delegate không thể tra cứu package-private hoặc private member.
- MODULE bị bỏ: delegate chỉ còn public access.
- PUBLIC bị bỏ: delegate không còn khả năng tạo handle truy cập member.

Giảm quyền theo nguyên tắc least privilege giúp giới hạn khả năng của component đang giữ Lookup.

## 13. Giảm quyền không thu hồi MethodHandle đã tạo

Một điểm bảo mật quan trọng: dropLookupMode chỉ ảnh hưởng Lookup mới. Nó không vô hiệu hóa các MethodHandle đã được tạo từ Lookup ban đầu.

~~~java
MethodHandles.Lookup full = MethodHandles.lookup();

MethodHandle privateGetter =
    full.findGetter(DropLookupModeDemo.class, "value", int.class);

MethodHandles.Lookup reduced =
    full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Dù reduced không còn PRIVATE access, privateGetter vẫn là capability riêng đã được tạo trước đó. Nếu đã chuyển privateGetter cho code khác, việc giảm quyền trên full hoặc tạo reduced không thu hồi handle đó.

Vì vậy:

- Giảm quyền trước khi chia sẻ Lookup.
- Không tạo sẵn handle nhạy cảm rồi cho rằng dropLookupMode sẽ thu hồi nó.
- Quản lý việc phát tán MethodHandle như quản lý một capability.
- Không chia sẻ Lookup đầy đủ nếu component chỉ cần một vài thao tác cụ thể; có thể truyền đúng MethodHandle cần thiết.

## 14. Kiểm tra Lookup bằng lookupModes và toString

lookupModes() là cách kiểm tra bit mask chính xác:

~~~java
int modes = lookup.lookupModes();

boolean hasPrivate =
    (modes & MethodHandles.Lookup.PRIVATE) != 0;
~~~

toString() cung cấp biểu diễn dễ đọc hơn cho log và debug, ví dụ suffix thể hiện public, module, package, private hoặc noaccess.

Không dùng toString() làm cơ chế authorization. Hãy kiểm tra lookupModes() hoặc thử tạo handle và xử lý IllegalAccessException theo hợp đồng API.

Khi log Lookup trong production, tránh đưa thông tin nội bộ nhạy cảm về class hoặc module ra log công khai.

## 15. Lỗi và ngoại lệ thường gặp

- IllegalArgumentException: mode truyền vào không nằm trong các mode hợp lệ của phiên bản Java đang chạy.
- IllegalAccessException: Lookup đã bị giảm quyền hoặc member không thể truy cập theo lookup class, package hay module.
- NoSuchFieldException hoặc NoSuchMethodException: member không tồn tại hoặc tên/kiểu/signature không khớp.
- Nhầm rằng dropLookupMode sửa Lookup ban đầu: API trả về Lookup mới; object ban đầu vẫn giữ quyền cũ.
- Nhầm rằng bỏ PRIVATE vẫn giữ PROTECTED: PROTECTED luôn bị loại khi gọi dropLookupMode trên Lookup thông thường.
- Nhầm rằng bỏ PACKAGE chỉ xóa một bit: PRIVATE cũng bị loại.
- Nhầm rằng bỏ MODULE chỉ xóa MODULE: PACKAGE và PRIVATE cũng bị loại.
- Nhầm rằng dropLookupMode thu hồi handle cũ: MethodHandle đã tạo vẫn có thể được gọi.
- Nhầm dropLookupMode với in: một API giữ lookup class, API kia chuyển lookup class.
- Chia sẻ Lookup đầy đủ không cần thiết: delegate có thể tạo handle vượt quá nhu cầu của nó.

## 16. Ví dụ hoàn chỉnh: kiểm tra và giảm quyền Lookup

Chương trình sau tạo Lookup đầy đủ, tạo một handle đọc private field, sau đó giảm quyền ở các mức PRIVATE, PACKAGE, MODULE và PUBLIC. Nó cũng chứng minh handle đã tạo trước đó vẫn hoạt động.

**Tệp DropLookupModeDemo.java:**

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class DropLookupModeDemo {
    private int value = 42;

    private static boolean has(int modes, int mode) {
        return (modes & mode) != 0;
    }

    private static String describe(MethodHandles.Lookup lookup) {
        int modes = lookup.lookupModes();
        return "PUBLIC=" + has(modes, MethodHandles.Lookup.PUBLIC)
                + ", PRIVATE=" + has(modes, MethodHandles.Lookup.PRIVATE)
                + ", PROTECTED=" + has(modes, MethodHandles.Lookup.PROTECTED)
                + ", PACKAGE=" + has(modes, MethodHandles.Lookup.PACKAGE)
                + ", MODULE=" + has(modes, MethodHandles.Lookup.MODULE);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup full = MethodHandles.lookup();
        MethodHandle existingGetter = full.findGetter(
                DropLookupModeDemo.class, "value", int.class);
        DropLookupModeDemo target = new DropLookupModeDemo();

        MethodHandles.Lookup noPrivate =
                full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        MethodHandles.Lookup noPackage =
                full.dropLookupMode(MethodHandles.Lookup.PACKAGE);
        MethodHandles.Lookup noModule =
                full.dropLookupMode(MethodHandles.Lookup.MODULE);
        MethodHandles.Lookup noPublic =
                full.dropLookupMode(MethodHandles.Lookup.PUBLIC);

        System.out.println("full: " + describe(full));
        System.out.println("drop PRIVATE: " + describe(noPrivate));
        System.out.println("drop PACKAGE: " + describe(noPackage));
        System.out.println("drop MODULE: " + describe(noModule));
        System.out.println("drop PUBLIC: " + describe(noPublic));

        try {
            noPrivate.findGetter(
                    DropLookupModeDemo.class, "value", int.class);
            throw new AssertionError("private lookup unexpectedly succeeded");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "reduced lookup cannot create private getter: true");
        }

        int value = (int) existingGetter.invokeExact(target);
        System.out.println("previously created handle still works: " + value);
    }
}
~~~

Biên dịch với API Java 9 và chạy trên JDK 17 trở lên:

~~~bash
javac --release 9 -Xlint:all DropLookupModeDemo.java
java DropLookupModeDemo
~~~

Output:

~~~text
full: PUBLIC=true, PRIVATE=true, PROTECTED=true, PACKAGE=true, MODULE=true
drop PRIVATE: PUBLIC=true, PRIVATE=false, PROTECTED=false, PACKAGE=true, MODULE=true
drop PACKAGE: PUBLIC=true, PRIVATE=false, PROTECTED=false, PACKAGE=false, MODULE=true
drop MODULE: PUBLIC=true, PRIVATE=false, PROTECTED=false, PACKAGE=false, MODULE=false
drop PUBLIC: PUBLIC=false, PRIVATE=false, PROTECTED=false, PACKAGE=false, MODULE=false
reduced lookup cannot create private getter: true
previously created handle still works: 42
~~~

Ví dụ cho thấy Lookup ban đầu vẫn giữ toàn bộ quyền của nó sau khi các bản giảm quyền được tạo. Bản noPrivate không thể tạo handle cho private field. MethodHandle existingGetter đã được tạo trước đó vẫn đọc được value, chứng minh việc giảm quyền không thu hồi capability đã phát ra.

## 17. Chọn mode theo nhu cầu

| Nhu cầu delegate | Cách tạo Lookup |
|---|---|
| Chỉ cần public access | drop MODULE |
| Cần public và module access, không cần package/private | drop PACKAGE |
| Cần package access nhưng không cần private | drop PRIVATE |
| Không muốn cho truy cập member nào | drop PUBLIC |
| Cần giữ nguyên quyền và lookup class | Không giảm quyền; chỉ chia sẻ cho code thực sự tin cậy |
| Cần chuyển lookup class | Lookup.in(newClass) |
| Cần private access cho class đích khi đủ điều kiện | MethodHandles.privateLookupIn |

Chọn quyền tối thiểu mà component cần. Nếu component chỉ cần gọi một thao tác, truyền một MethodHandle cụ thể có thể dễ kiểm soát hơn truyền cả Lookup.

## 18. Ghi nhớ

dropLookupMode là API Java 9 để giảm quyền của MethodHandles.Lookup trước khi delegate. Nó giữ nguyên lookup class, tạo một Lookup mới và không sửa object ban đầu. Bỏ PACKAGE cũng bỏ PRIVATE; bỏ MODULE cũng bỏ PACKAGE và PRIVATE; bỏ PUBLIC làm Lookup không còn quyền truy cập. PROTECTED và UNCONDITIONAL bị loại khỏi Lookup thông thường. Dùng lookupModes() để kiểm tra quyền. Quan trọng nhất, dropLookupMode không thu hồi MethodHandle đã tạo trước đó, vì vậy hãy giảm quyền trước khi chia sẻ Lookup hoặc phát hành handle nhạy cảm.

## 19. Tài liệu tham khảo

- [MethodHandles.Lookup – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [MethodHandles.Lookup – Java SE 9 API](https://cr.openjdk.org/~jjg/java-javafx-jdk-docs/api/java/lang/invoke/MethodHandles.Lookup.html)
