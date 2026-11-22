# Không thu hẹp phạm vi truy cập khi ghi đè phương thức trong Java

Một override phải giữ nguyên hoặc **mở rộng** quyền truy cập của phương thức bị ghi đè. Nếu lớp cha công khai một phương thức public, lớp con không thể làm phương thức đó thành protected hoặc package-private: mã gọi hợp lệ qua kiểu cha phải tiếp tục làm việc khi đối tượng thực là lớp con.

## 1. Quy tắc visibility

| Phương thức cha | Visibility hợp lệ ở override | Không hợp lệ |
| --- | --- | --- |
| public | public | protected, package-private, private |
| protected | protected, public | package-private, private |
| Package-private | Giữ nguyên hoặc mở rộng khi thực sự override được | private; hoặc trường hợp khác package không kế thừa phương thức đó |
| private | Không có override đối với phương thức private đó | Không áp dụng thang visibility |

Trong class, bỏ modifier nghĩa là package-private. Phương thức private của cha không được kế thừa để override; phương thức cùng tên trong con là khai báo riêng. Với package-private, cần xét package: subclass ở package khác không nhìn thấy phương thức đó để override. Nếu phương thức package-private là abstract, subclass concrete ở package khác không thể đáp ứng hợp đồng bằng cách chỉ khai báo một phương thức trùng tên.

## 2. Ví dụ: mở rộng quyền truy cập

~~~java
package academy.reports;

public abstract class Report {
    public abstract String title();
    protected abstract int pages();
    abstract String marker();
}
~~~

~~~java
package academy.reports;

public final class MonthlyReport extends Report {
    @Override
    public String title() {
        return "Monthly";
    }

    @Override
    public int pages() {          // protected -> public
        return 12;
    }

    @Override
    protected String marker() {   // package-private -> protected
        return "2026-10";
    }
}
~~~

Hai lớp ở cùng package nên MonthlyReport.marker() thực sự override được phương thức package-private của cha. pages() được mở thành public để caller ngoài package có thể gọi qua kiểu MonthlyReport.

Dù MonthlyReport.pages() là public, lời gọi report.pages() qua biến có kiểu tĩnh Report ở một package khác vẫn không hợp lệ, vì khai báo nhìn thấy qua Report là protected. Quyền truy cập được kiểm tra lúc biên dịch theo kiểu tĩnh và quy tắc protected; đối tượng runtime không tự nâng quyền cho lời gọi.

## 3. Interface luôn yêu cầu public cho instance method

~~~java
interface Sender {
    void send(); // public abstract ngầm định
}

final class EmailSender implements Sender {
    @Override
    public void send() {
        System.out.println("sent");
    }
}
~~~

Class triển khai không được bỏ public khỏi send(): trong class, method không modifier là package-private, yếu hơn hợp đồng public của interface. Quy tắc tương tự áp dụng khi override default method public.

## 4. Chẩn đoán lỗi

~~~java
class Document {
    public String name() { return "Document"; }
}

class PdfDocument extends Document {
    @Override
    protected String name() { return "PDF"; } // Không hợp lệ
}
~~~

Compiler thường báo lỗi về *weaker access privileges*. Bỏ @Override không sửa được lỗi; bản khai báo vẫn đang override với quyền truy cập yếu hơn.

**Checklist:** so sánh visibility ở phương thức cha/interface với phương thức con; kiểm tra package nếu cha dùng package-private; và không nhầm quyền truy cập với dispatch runtime. Bài này tập trung vào visibility; tính tương thích của return type và checked exceptions được giải thích ở các bài riêng.