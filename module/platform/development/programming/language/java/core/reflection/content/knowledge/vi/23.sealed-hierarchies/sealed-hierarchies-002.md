# Các lớp hoặc interface con trực tiếp được phép trong phân cấp sealed

## 1. “Trực tiếp” là một quan hệ, không phải mọi kiểu con

Một kiểu sealed kiểm soát những lớp hoặc interface được phép nằm **ngay dưới nó** trong quan hệ kế thừa. Các kiểu ở sâu hơn chịu ràng buộc của nhánh trung gian tương ứng.

Ví dụ, nếu `MobileWallet` triển khai `Wallet`, còn `Wallet` mở rộng `PaymentMethod`, thì `MobileWallet` là một loại `PaymentMethod` nhưng không phải kiểu con trực tiếp của `PaymentMethod`.

Phân biệt này rất quan trọng khi đọc:

~~~java
Class<?>[] children = parent.getPermittedSubclasses();
~~~

Đây là đoạn minh họa trong một phương thức có biến `Class<?> parent`. Kết quả, khi parent là sealed, mô tả các kiểu con **trực tiếp được phép** có thể thu được ở môi trường chạy. Nó không tự làm phẳng toàn bộ phân cấp thành một danh sách.

Một công cụ hiển thị mô hình, kiểm tra kiến trúc hoặc chọn các nhánh xử lý cần giữ đúng quan hệ này. Nếu coi mọi kiểu con gián tiếp là một mục trực tiếp, công cụ đã thay đổi ý nghĩa của mô hình.

## 2. permits và extends/implements đảm nhiệm hai phần khác nhau

`permits` chỉ ra ai được phép là kiểu con trực tiếp. `extends` hoặc `implements` khai báo quan hệ kiểu thực tế từ phía kiểu con.

| Kiểu cha sealed | Kiểu con trực tiếp hợp lệ | Cách kiểu con khai báo quan hệ |
| --- | --- | --- |
| Một class | Một class | `extends Parent` |
| Một interface | Một class | `implements Parent` |
| Một interface | Một interface | `extends Parent` |

Một interface không thể kế thừa một class, nên danh sách permitted của một sealed class không trở thành danh sách interface triển khai nó.

Chỉ liệt kê một tên trong `permits` không tự làm lớp ấy kế thừa hoặc triển khai kiểu cha. Ngược lại, một kiểu không được cho phép không thể tự bổ sung quan hệ trực tiếp với một kiểu sealed bằng cách chỉ viết `extends` hoặc `implements`.

Kiểu con trực tiếp cũng cần xác định khả năng mở rộng tiếp:

- Class `final`: dừng kế thừa ở class ấy.
- Class hoặc interface `sealed`: tiếp tục kiểm soát các kiểu con trực tiếp của chính nó.
- Class hoặc interface `non-sealed`: mở lại việc mở rộng ở nhánh ấy.
- Một số dạng khai báo có tính chất ngầm định phù hợp, chẳng hạn record là final.

Interface không dùng `final`. Nếu là interface con trực tiếp của sealed interface, nó tiếp tục theo hướng sealed hoặc non-sealed.

## 3. Ví dụ chạy được: danh sách có cả class và interface

Lưu thành `DirectPermittedTypesDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class DirectPermittedTypesDemo {
    sealed interface PaymentMethod
            permits Card, Wallet, ExternalPayment {
    }

    record Card(String network) implements PaymentMethod {
    }

    sealed interface Wallet extends PaymentMethod
            permits MobileWallet, BrowserWallet {
    }

    record MobileWallet(String account) implements Wallet {
    }

    record BrowserWallet(String account) implements Wallet {
    }

    static non-sealed class ExternalPayment implements PaymentMethod {
    }

    static final class VendorPayment extends ExternalPayment {
    }

    private static boolean hasDirectRelation(
            Class<?> parent, Class<?> candidate) {
        if (parent.isInterface()) {
            return Arrays.asList(candidate.getInterfaces()).contains(parent);
        }
        return candidate.getSuperclass() == parent;
    }

    private static String childNames(Class<?> sealedType) {
        return Arrays.stream(sealedType.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Class<?> root = PaymentMethod.class;
        Class<?>[] children = root.getPermittedSubclasses();
        Arrays.sort(children, Comparator.comparing(Class::getName));

        System.out.println("PaymentMethod.children="
                + childNames(root));

        for (Class<?> child : children) {
            System.out.println(child.getSimpleName()
                    + ": kind=" + (child.isInterface() ? "interface" : "class")
                    + ", direct=" + hasDirectRelation(root, child));
        }

        System.out.println("Wallet.children=" + childNames(Wallet.class));
        System.out.println("MobileWallet.directToRoot="
                + hasDirectRelation(root, MobileWallet.class));
        System.out.println("MobileWallet.assignableToRoot="
                + root.isAssignableFrom(MobileWallet.class));
        System.out.println("VendorPayment.directToRoot="
                + hasDirectRelation(root, VendorPayment.class));
        System.out.println("VendorPayment.assignableToRoot="
                + root.isAssignableFrom(VendorPayment.class));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 DirectPermittedTypesDemo.java
java DirectPermittedTypesDemo
~~~

Kết quả:

~~~text
PaymentMethod.children=Card,ExternalPayment,Wallet
Card: kind=class, direct=true
ExternalPayment: kind=class, direct=true
Wallet: kind=interface, direct=true
Wallet.children=BrowserWallet,MobileWallet
MobileWallet.directToRoot=false
MobileWallet.assignableToRoot=true
VendorPayment.directToRoot=false
VendorPayment.assignableToRoot=true
~~~

Ba điểm quan trọng:

1. `getPermittedSubclasses()` trên một interface có thể trả một interface con như `Wallet`, dù tên API chứa chữ “Subclasses”.
2. `MobileWallet` thuộc nhánh `Wallet`, còn `VendorPayment` thuộc nhánh `ExternalPayment`. Cả hai không có trong danh sách trực tiếp của root.
3. `isAssignableFrom` chấp nhận quan hệ gián tiếp, nên hai kiểu ấy vẫn gán được về `PaymentMethod`.

Hàm `childNames` trong ví dụ chỉ được gọi với các kiểu đã biết là sealed. Nếu dùng cho một Class bất kỳ, phải xử lý trường hợp `getPermittedSubclasses()` trả `null`.

Việc sắp xếp được thực hiện để bản in ổn định. Không lấy thứ tự mảng Reflection trả về làm thứ tự bắt buộc của danh sách trong mã nguồn.

## 4. Kiểm chứng một cạnh trực tiếp bằng Reflection

Có thể quan sát quan hệ từ phía kiểu con:

- Với cha là class, `candidate.getSuperclass() == parent` kiểm tra lớp cha trực tiếp.
- Với cha là interface, `candidate.getInterfaces()` cho các interface trực tiếp mà candidate triển khai hoặc mở rộng.
- `parent.isAssignableFrom(candidate)` trả lời quan hệ kiểu rộng hơn, bao gồm gián tiếp.

Ví dụ `VendorPayment` kế thừa `ExternalPayment`. Nó nhận quan hệ với `PaymentMethod` qua lớp cha, nhưng không có `PaymentMethod` trong danh sách interface trực tiếp của chính nó.

Một lớp có thể trực tiếp triển khai nhiều interface. Nếu nhiều interface ấy đều sealed, quan hệ trực tiếp phải hợp lệ đối với từng interface tương ứng. Vì vậy, phân cấp interface có thể là một đồ thị, không luôn là một cây có đúng một cha.

Hàm `hasDirectRelation` ở trên minh họa cách đọc các cạnh. Nó không phải cách cấp phép mới hoặc cách vượt qua quy tắc sealed. Với kết quả hợp lệ trả từ `getPermittedSubclasses()`, API đã dùng khái niệm kiểu con trực tiếp; công cụ có thể đọc cạnh ngược để giải thích và kiểm tra dữ liệu của mình.

Nếu cần duyệt sâu hơn, hãy giữ riêng từng cạnh cha–con và gọi tiếp trên nhánh sealed. Không đưa mọi hậu duệ vào cùng danh sách con trực tiếp của root chỉ để làm giao diện đơn giản hơn.

## 5. Danh sách có thể được suy ra mà không viết permits

Một khai báo sealed có thể không viết mệnh đề `permits` nếu trình biên dịch suy ra được các kiểu con trực tiếp theo quy tắc trong cùng đơn vị biên dịch. Với class sealed thông thường, các class có tên chuẩn phù hợp, được khai báo trong cùng đơn vị biên dịch và trực tiếp `extends` class ấy được dùng để suy ra danh sách.

Reflection vẫn đọc được danh sách permitted đã được ghi trong kết quả biên dịch. Nó không yêu cầu ứng dụng phân tích lại văn bản nguồn để tìm từ khóa `permits`.

Lưu thành `InferredDirectChildrenDemo.java`:

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class InferredDirectChildrenDemo {
    static abstract sealed class Document {
    }

    static final class Invoice extends Document {
    }

    static abstract sealed class Report extends Document
            permits SummaryReport {
    }

    static final class SummaryReport extends Report {
    }

    private static String childNames(Class<?> type) {
        return Arrays.stream(type.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("Document.children="
                + childNames(Document.class));
        System.out.println("Report.children="
                + childNames(Report.class));
        System.out.println("Document.memberClasses="
                + Document.class.getDeclaredClasses().length);
        System.out.println("SummaryReport.directToDocument="
                + (SummaryReport.class.getSuperclass() == Document.class));
        System.out.println("Document.assignableFromSummaryReport="
                + Document.class.isAssignableFrom(SummaryReport.class));
        System.out.println("Invoice.superclass="
                + Invoice.class.getSuperclass().getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 InferredDirectChildrenDemo.java
java InferredDirectChildrenDemo
~~~

Kết quả:

~~~text
Document.children=Invoice,Report
Report.children=SummaryReport
Document.memberClasses=0
SummaryReport.directToDocument=false
Document.assignableFromSummaryReport=true
Invoice.superclass=Document
~~~

`Document` không viết `permits`, nhưng hai lớp `Invoice` và `Report` trực tiếp kế thừa nó trong cùng tệp. Danh sách của `Document` không chứa `SummaryReport`, vì lớp ấy có cha trực tiếp là `Report`.

Các lớp đều được lồng trong lớp ngoài `InferredDirectChildrenDemo` để ví dụ nằm gọn trong một tệp. Chúng là các thành viên của lớp ngoài; không phải các lớp thành viên được khai báo bên trong `Document`.

Vì thế, `Document.class.getDeclaredClasses()` trả mảng rỗng trong ví dụ. **Lớp thành viên** và **lớp con kế thừa** là hai loại quan hệ khác nhau. `getDeclaredClasses()` không phải API thay thế cho danh sách permitted.

## 6. Ranh giới khai báo của các kiểu trực tiếp

Việc đặt các kiểu trong ví dụ không chỉ nhằm thuận tiện cho việc đọc. Java áp dụng ràng buộc về nơi khai báo các kiểu con trực tiếp được phép:

- Với kiểu sealed trong một named module, các kiểu trực tiếp được phép phải thuộc cùng module.
- Với kiểu sealed trong unnamed module, chúng phải thuộc cùng package.

Trong named module, cùng module không nhất thiết đồng nghĩa cùng package; những quy tắc truy cập và tham chiếu kiểu liên quan vẫn cần được thỏa mãn.

Mục đích là giữ ranh giới mở rộng trực tiếp trong phạm vi quản lý của mô hình. Một lớp ở ngoài không thể tự trở thành nhánh trực tiếp mới chỉ bằng việc xuất hiện trên classpath.

Đối với nhánh `non-sealed`, các kiểu ở sâu hơn không phải được thêm từng tên vào permitted của root. Trong ví dụ đầu, `VendorPayment` mở rộng `ExternalPayment`; nó không cần và không nên được coi là một phần tử trực tiếp của `PaymentMethod`.

Nếu muốn thay đổi ai là kiểu con trực tiếp, đó là thay đổi khai báo kiểu và kết quả biên dịch tương ứng. Sửa một mảng `Class<?>[]` đã nhận từ Reflection không cập nhật quyền kế thừa của JVM.

## 7. Điều kết quả permitted có và không có

Một phần tử trong danh sách cho biết quan hệ kiểu trực tiếp được phép; nó chưa trả lời toàn bộ các câu hỏi khác:

| Câu hỏi | Có được suy ra chỉ từ việc có trong danh sách không? |
| --- | --- |
| Đây là nhánh trực tiếp của kiểu sealed đang xét? | Có, đối với phần tử hợp lệ được API trả về |
| Đây chắc chắn là class? | Không; với cha là interface, có thể là interface |
| Đây chắc chắn là kiểu cụ thể có thể tạo instance? | Không; có thể là abstract hoặc interface |
| Có constructor public không tham số? | Không |
| Có đối tượng của kiểu ấy đang sống? | Không |
| Kiểu ấy đã được đăng ký làm bean/plugin trong ứng dụng? | Không |
| Mọi kiểu con sâu hơn đều nằm trong mảng này? | Không |

API cố gắng lấy các đối tượng `Class` cho những kiểu permitted bằng bộ nạp định nghĩa của kiểu cha. Mục không lấy được Class có thể bị bỏ qua theo hợp đồng API. Vì vậy, khi cần một báo cáo kiểm toán đầy đủ mọi tên trong metadata nhị phân, phải xét thêm class file và môi trường nạp, không chỉ nhìn mảng kết quả.

Với kiểu không sealed, phương thức trả `null`. Với kiểu sealed, nó trả một mảng khác null nhưng có thể rỗng theo hợp đồng. Giữ nguyên sự phân biệt này nếu công cụ cần biết kiểu đang mở hay sealed nhưng chưa thu được phần tử.

Việc lấy danh sách không phải bước tạo đối tượng. Một công cụ xem quan hệ kiểu có thể làm việc với tên, loại kiểu và cạnh trực tiếp mà không gọi constructor của các kiểu trong mảng.

## 8. Cách trình bày và kiểm tra mô hình cho đúng

Khi xây công cụ dùng danh sách permitted, một quy trình rõ ràng là:

1. Xác nhận kiểu cha và tình trạng sealed.
2. Lấy các phần tử trực tiếp.
3. Phân loại mỗi phần tử là class hay interface.
4. Giữ quan hệ trực tiếp và đối tượng `Class` làm danh tính kiểu trong JVM.
5. Nếu cần, mở rộng riêng các nút sealed, đánh dấu rõ nhánh non-sealed hoặc điểm chưa đủ thông tin.
6. Sắp xếp cách trình bày theo quy tắc tường minh.

Tên đơn giản phù hợp cho các ví dụ ngắn, nhưng không phải khóa duy nhất của mọi kiểu trong một ứng dụng. Các package hoặc bộ nạp lớp khác nhau có thể tạo những kiểu có tên hiển thị giống nhau. Không ghép nhầm hai nút chỉ vì `getSimpleName()` trùng nhau.

Nếu kiểm tra mô hình trong một bài kiểm thử, nên so sánh tập kiểu trực tiếp mong đợi, hoặc các quan hệ cần thiết. Không đóng cứng thứ tự mảng do API trả về. Nếu ứng dụng cần bảo đảm các lớp được đóng gói đầy đủ, hãy xác minh môi trường cung cấp chúng thay vì tự coi một mục bị thiếu là bằng chứng rằng mã nguồn không từng cho phép mục ấy.

Cũng không tự khởi tạo từng class chỉ để “xác nhận nó được phép”. Việc nằm trong phân cấp và việc tạo đối tượng hợp lệ là các bước có hợp đồng khác nhau.

## 9. Tự kiểm tra

1. `MobileWallet` là một loại `PaymentMethod`; vì sao nó không ở danh sách trực tiếp của `PaymentMethod`?
2. Tên API chứa “Subclasses” có loại trừ interface con không?
3. Một class được liệt kê trong `permits` có thể bỏ `extends`/`implements` rồi tự nhận quan hệ nhờ danh sách ấy không?
4. `getDeclaredClasses()` có thể dùng để tìm mọi kiểu con permitted không?
5. Không thấy mệnh đề `permits` trong nguồn có đủ để kết luận Reflection không thể trả danh sách không?
6. Một lớp con của nhánh non-sealed có phải được đưa vào permitted trực tiếp của root không?

Đáp án:

1. Nó triển khai trực tiếp `Wallet`; quan hệ với `PaymentMethod` đi qua nhánh ấy.
2. Không. Sealed interface có thể cho phép cả class triển khai trực tiếp và interface mở rộng trực tiếp.
3. Không. Danh sách cấp phép và khai báo quan hệ phải phù hợp với nhau.
4. Không. Đó là API về kiểu thành viên được khai báo bên trong một kiểu.
5. Không. Trình biên dịch có thể suy ra danh sách theo các quy tắc tương ứng.
6. Không. Nó nằm sâu hơn trong nhánh; không tự trở thành cạnh trực tiếp của root.

## Tài liệu đối chiếu

- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
- [Java 17 — Class.getInterfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getInterfaces()).
- [JLS 17 — Các lớp con trực tiếp được phép](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [JLS 17 — Class và interface con trực tiếp của sealed interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
