# Giới hạn khi dùng `record` hoặc `enum` trong phân cấp `sealed`

## Mục tiêu

Từ Java 17, `sealed class` và `sealed interface` cho phép khai báo rõ những kiểu nào được phép kế thừa hoặc triển khai trực tiếp. `record` và `enum` có các quy tắc kế thừa riêng, vì vậy chúng phù hợp làm nhánh lá của một phân cấp sealed theo những cách nhất định, nhưng không thể thay thế tùy ý một lớp cơ sở.

Điểm cần nhớ: **record và enum có thể triển khai một sealed interface; chúng không thể kế thừa một sealed class do người dùng định nghĩa.**

## 1. Quy tắc của phân cấp sealed

Một lớp hoặc interface được khai báo `sealed` phải xác định các kiểu con trực tiếp được phép bằng mệnh đề `permits`, hoặc để trình biên dịch suy luận danh sách đó khi các kiểu con trực tiếp phù hợp được khai báo trong cùng compilation unit.

Ví dụ:

```java
sealed interface KetQua permits ThanhCong, ThatBai, TrangThai {
}
```

Các kiểu được liệt kê phải là kiểu con trực tiếp của `KetQua`: một lớp phải `implements KetQua`, hoặc một interface khác phải `extends KetQua`. Không liệt kê kiểu cháu chỉ kế thừa thông qua một kiểu trung gian.

Mỗi lớp con trực tiếp của một sealed class phải là `final`, `sealed` hoặc `non-sealed`. Với sealed interface, quy tắc tương tự áp dụng cho các lớp triển khai trực tiếp và các interface mở rộng trực tiếp. Mục đích là để mỗi nhánh tiếp tục đóng hoặc chủ động mở rộng phân cấp một cách rõ ràng.

Các kiểu được phép kế thừa hoặc triển khai phải ở cùng module với kiểu sealed khi dùng named module; nếu ứng dụng nằm trong unnamed module, chúng phải ở cùng package. Vi phạm điều kiện này sẽ khiến chương trình không biên dịch.

## 2. Vì sao record không thể là lớp con của sealed class?

Một record luôn kế thừa trực tiếp từ `java.lang.Record`. Cú pháp khai báo record không cho phép chọn một lớp cha khác. Record cũng **ngầm định là `final`**, vì vậy không thể khai báo nó thành `sealed` hay `non-sealed`, cũng không thể tạo lớp con từ record.

Do đó, record không thể trực tiếp mở rộng một sealed class tùy chỉnh. Dù sealed class có liệt kê tên record trong `permits`, điều đó cũng không thay đổi quy tắc lớp cha cố định của record.

Record có thể triển khai một interface thông thường hoặc sealed interface. Đây là cách phù hợp để biểu diễn một nhánh dữ liệu bất biến trong phân cấp kiểu đóng.

```java
sealed interface ThongTin permits NguoiDung {
}

record NguoiDung(String ten, int tuoi) implements ThongTin {
}
```

Trong ví dụ này, `NguoiDung` là một kiểu con trực tiếp hợp lệ của `ThongTin`. Record không cần khai báo `final` vì tính chất đó đã được ngôn ngữ áp dụng ngầm định.

Nếu cần dùng chung trạng thái hoặc hành vi từ một lớp cơ sở, hãy dùng một lớp thông thường làm nhánh con của sealed class. Nếu mô hình chủ yếu là các biến thể dữ liệu, sealed interface kết hợp với record thường đơn giản hơn.

## 3. Vì sao enum không thể là lớp con của sealed class?

Mọi enum đều kế thừa từ `java.lang.Enum`, và Java không cho phép enum mở rộng một lớp khác. Vì thế, enum không thể trực tiếp kế thừa một sealed class do ứng dụng định nghĩa.

Enum có thể triển khai nhiều interface, kể cả sealed interface. Điều này hữu ích khi các giá trị hữu hạn như trạng thái hoặc loại sự kiện cần tham gia cùng một mô hình kết quả.

```java
sealed interface TrangThaiXuLy permits TrangThaiDonHang {
}

enum TrangThaiDonHang implements TrangThaiXuLy {
    MOI,
    DANG_XU_LY,
    HOAN_TAT
}
```

Khi không có hằng enum nào khai báo class body riêng, enum ngầm định là `final`. Nếu ít nhất một hằng enum có class body riêng, kiểu enum được xem là ngầm định `sealed`; các lớp ẩn danh gắn với những hằng đó là các lớp con do trình biên dịch tạo ra. Trường hợp này không biến enum thành một lớp có thể được người dùng tùy ý kế thừa, và không cho phép enum mở rộng một sealed class tùy chỉnh.

## 4. Ví dụ hoàn chỉnh: sealed interface kết hợp record và enum

Ví dụ dưới đây chạy độc lập trên Java 17 trở lên. Hai record mang dữ liệu cho các kết quả khác nhau, còn enum biểu diễn một trạng thái cố định. Cả ba đều triển khai cùng một sealed interface.

Lưu nội dung vào tệp `SealedRecordEnumDemo.java`:

```java
import java.util.List;

public class SealedRecordEnumDemo {
    public static void main(String[] args) {
        List<KetQua> ketQua = List.of(
            new ThanhCong("OK", 200),
            new ThatBai("NOT_FOUND", 404),
            TrangThai.DANG_XU_LY
        );

        for (KetQua item : ketQua) {
            System.out.println(moTa(item));
        }
    }

    private static String moTa(KetQua item) {
        if (item instanceof ThanhCong t) {
            return "Thành công: " + t.ma() + " (" + t.httpCode() + ")";
        }
        if (item instanceof ThatBai f) {
            return "Thất bại: " + f.ma() + " (" + f.httpCode() + ")";
        }
        if (item instanceof TrangThai s) {
            return "Trạng thái: " + s.name();
        }

        throw new IllegalStateException(
            "Loại kết quả chưa được xử lý: " + item.getClass().getName()
        );
    }
}

sealed interface KetQua permits ThanhCong, ThatBai, TrangThai {
}

record ThanhCong(String ma, int httpCode) implements KetQua {
}

record ThatBai(String ma, int httpCode) implements KetQua {
}

enum TrangThai implements KetQua {
    DANG_XU_LY
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 SealedRecordEnumDemo.java
java SealedRecordEnumDemo
```

Kết quả chuẩn trên đầu ra:

```text
Thành công: OK (200)
Thất bại: NOT_FOUND (404)
Trạng thái: DANG_XU_LY
```

Ví dụ cho thấy sealed interface kiểm soát tập kiểu triển khai trực tiếp, trong khi record và enum vẫn giữ các quy tắc riêng của chúng. Câu lệnh `instanceof` dùng cú pháp pattern matching đã được hỗ trợ chính thức từ Java 16, nên ví dụ không cần tính năng preview.

## 5. Những thiết kế không hợp lệ và cách chọn mô hình

| Nhu cầu | Cách thiết kế phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Một biến thể dữ liệu gồm các trường cố định | Record triển khai sealed interface | Record không thể kế thừa lớp cơ sở tùy chỉnh |
| Một tập trạng thái hữu hạn, có tên cố định | Enum triển khai sealed interface | Enum không thể kế thừa lớp cơ sở tùy chỉnh |
| Các nhánh cần kế thừa trạng thái hoặc hành vi từ lớp cha | Các lớp thông thường được liệt kê trong `permits` | Mỗi lớp con trực tiếp phải là `final`, `sealed` hoặc `non-sealed` |
| Một nhánh cần mở rộng tiếp nhưng vẫn kiểm soát các kiểu con | Một sealed class hoặc sealed interface trung gian | Kiểu trung gian cũng phải khai báo các nhánh hợp lệ của nó |
| Cần cho phép bên ngoài bổ sung lớp con | Một nhánh `non-sealed` hoặc thiết kế interface không sealed | Nhánh `non-sealed` mở phần phân cấp đó ra khỏi danh sách đóng |

Không thể khai báo một record theo dạng `record ChiTiet(...) extends LopCoSo`: record không có mệnh đề `extends` cho lớp ứng dụng. Tương tự, khai báo enum để mở rộng `LopCoSo` là không hợp lệ vì enum đã kế thừa `java.lang.Enum`.

Một lỗi thường gặp khác là đưa kiểu không phải con trực tiếp vào `permits`, hoặc đặt kiểu được phép ở sai package/module. Hãy kiểm tra quan hệ kế thừa thực tế và vị trí khai báo của từng kiểu trước khi điều tra các lỗi khác.

## 6. Cách kiểm tra khi biên dịch báo lỗi

1. Xác định kiểu cha là sealed class hay sealed interface.
2. Với từng mục trong `permits`, kiểm tra kiểu đó có trực tiếp `extends` hoặc `implements` kiểu sealed hay không.
3. Nếu kiểu con là record hoặc enum, kiểm tra nó có đang cố kế thừa một lớp ứng dụng hay không. Trường hợp đó cần đổi mô hình sang sealed interface hoặc dùng lớp con thông thường.
4. Với lớp con trực tiếp thông thường, kiểm tra modifier `final`, `sealed` hoặc `non-sealed`.
5. Kiểm tra các điều kiện cùng module/package và tên kiểu trong `permits`.
6. Biên dịch lại toàn bộ các tệp liên quan cùng phiên bản JDK phù hợp; không kết luận từ một tệp riêng nếu các kiểu phụ thuộc chưa được biên dịch.

Trong Java 17, sealed classes/interfaces và records đã là tính năng chính thức. Nếu muốn dùng `switch` với pattern matching trên phân cấp sealed, hãy lưu ý rằng pattern matching for switch chỉ trở thành tính năng chính thức ở Java 21; trên Java 17 nó còn là tính năng preview. Các ví dụ trong bài dùng `instanceof` để chạy mà không cần bật preview.

## Ghi nhớ

- **Record → sealed interface:** hợp lệ; record là nhánh lá ngầm định `final`.
- **Enum → sealed interface:** hợp lệ; enum biểu diễn tập hằng hữu hạn và có thể ngầm định `final` hoặc `sealed` tùy class body của các hằng.
- **Record → sealed class tùy chỉnh:** không hợp lệ vì record chỉ kế thừa `java.lang.Record`.
- **Enum → sealed class tùy chỉnh:** không hợp lệ vì enum chỉ kế thừa `java.lang.Enum`.
- **Sealed class → lớp con thông thường:** hợp lệ nếu lớp con được cho phép và tuân thủ quy tắc modifier cùng điều kiện module/package.

Hãy chọn sealed interface khi muốn kết hợp nhiều kiểu lá khác nhau như record và enum; chọn sealed class khi các nhánh cần chia sẻ một lớp cha cụ thể.