# Bài toán giao diện đa nền tảng với Button và Checkbox cùng phong cách

> **Chương:** Nhận diện bài toán  
> **Học phần:** Học về Abstract Factory trong Design Pattern — `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`.  
> **Trọng tâm:** Nhận ra nhu cầu tạo **một họ đối tượng liên quan và tương thích với nhau** khi giao diện phải chạy trên nhiều nền tảng.

## 1. Tình huống: một màn hình đăng nhập, nhiều nền tảng

Giả sử nhóm phát triển một ứng dụng desktop chạy trên **Windows** và **macOS**. Màn hình đăng nhập có hai thành phần:

- **Button**: nút **Đăng nhập** để người dùng gửi thông tin.
- **Checkbox**: ô **Ghi nhớ đăng nhập** để người dùng bật hoặc tắt lựa chọn.

Chức năng của hai thành phần về cơ bản không đổi giữa các hệ điều hành: Button nhận thao tác nhấn, Checkbox cho phép chọn hoặc bỏ chọn. Tuy nhiên, mỗi nền tảng có phong cách giao diện riêng: cách vẽ, kích thước, trạng thái hover/focus, khoảng cách, hiệu ứng và cách phản hồi tương tác có thể khác nhau.

Yêu cầu của sản phẩm là:

| Nền tảng đang sử dụng | Button cần hiển thị | Checkbox cần hiển thị |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |

Các thành phần phải **cùng thuộc phong cách của nền tảng đã chọn**. Một màn hình có nút theo Windows nhưng ô chọn theo macOS trông thiếu nhất quán, dù cả hai thành phần vẫn hoạt động đúng khi đứng riêng lẻ.

Đây là điểm làm bài toán khác việc tạo một Button thông thường: hệ thống cần chọn **cả một bộ thành phần có quan hệ với nhau**, không chỉ chọn một lớp để khởi tạo.

## 2. Điều kiện đúng của giao diện: tính nhất quán theo họ

Hãy xem `WindowsButton` và `WindowsCheckbox` là các sản phẩm thuộc **họ Windows**; `MacButton` và `MacCheckbox` thuộc **họ macOS**.

| Tổ hợp thành phần trong cùng màn hình | Đánh giá | Lý do |
| --- | --- | --- |
| `WindowsButton` + `WindowsCheckbox` | Hợp lệ | Cùng họ Windows |
| `MacButton` + `MacCheckbox` | Hợp lệ | Cùng họ macOS |
| `WindowsButton` + `MacCheckbox` | Không hợp lệ | Trộn hai họ giao diện |
| `MacButton` + `WindowsCheckbox` | Không hợp lệ | Trộn hai họ giao diện |

Có thể diễn tả bất biến (*invariant*) của màn hình như sau:

~~~text
family(button) == family(checkbox) == selectedPlatform
~~~

Ở đây, `family(...)` là cách ký hiệu họ giao diện của thành phần, còn `selectedPlatform` là nền tảng mà ứng dụng đã quyết định sử dụng. Đây là **quy tắc thiết kế** để kiểm tra tính nhất quán, không bắt buộc là một phương thức thật trong mã nguồn.

Quy tắc này cần được duy trì khi mở màn hình mới, thêm thành phần khác hoặc đổi nền tảng. Chỉ kiểm tra rằng “Button bấm được” và “Checkbox chọn được” là chưa đủ.

### Hai chiều biến thể xuất hiện đồng thời

Bài toán có **hai chiều** cần phân biệt:

1. **Loại sản phẩm**: Button, Checkbox; về sau có thể thêm TextField, Dropdown, RadioButton.
2. **Họ sản phẩm**: Windows, macOS; về sau có thể thêm Linux.

Mỗi họ cung cấp một phiên bản tương ứng của các loại sản phẩm:

~~~text
                     Loại sản phẩm
                 Button       Checkbox
Họ Windows    WindowsButton  WindowsCheckbox
Họ macOS      MacButton      MacCheckbox
~~~

**Yêu cầu quan trọng:** khi chọn một hàng trong bảng (một họ), ứng dụng phải tạo các thành phần trong đúng hàng đó. Nếu logic chọn Button và Checkbox nằm rải rác, không có gì tự động bảo đảm điều này.

## 3. Cách làm ban đầu và lỗi dễ xảy ra

Một cách triển khai trực tiếp là kiểm tra nền tảng mỗi khi cần khởi tạo một thành phần:

~~~java
Button loginButton = (platform == Platform.WINDOWS)
        ? new WindowsButton()
        : new MacButton();

Checkbox rememberMe = (platform == Platform.WINDOWS)
        ? new WindowsCheckbox()
        : new MacCheckbox();
~~~

Đoạn mã có thể đáp ứng hai nền tảng hiện tại, nhưng phần sử dụng giao diện đã phải biết tên những lớp cụ thể. Quan trọng hơn, mỗi thành phần được chọn **độc lập**. Khi giao diện lớn lên và các nhánh lựa chọn nằm ở những lớp khác nhau, rất dễ có một nhánh dùng cấu hình khác hoặc bị bỏ sót khi cập nhật.

Ví dụ Java sau mô phỏng một lỗi như vậy. Để tập trung vào bài toán tạo đối tượng, phương thức `appearance()` đại diện cho kết quả hiển thị; đây chưa phải bộ điều khiển UI thực tế.

~~~java
public class MixedUiDemo {
    enum Platform { WINDOWS, MACOS }

    interface Button {
        String appearance();
    }

    interface Checkbox {
        String appearance();
    }

    static final class WindowsButton implements Button {
        public String appearance() { return "WindowsButton"; }
    }

    static final class MacButton implements Button {
        public String appearance() { return "MacButton"; }
    }

    static final class WindowsCheckbox implements Checkbox {
        public String appearance() { return "WindowsCheckbox"; }
    }

    static final class MacCheckbox implements Checkbox {
        public String appearance() { return "MacCheckbox"; }
    }

    public static void main(String[] args) {
        Platform operatingSystem = Platform.WINDOWS;
        Platform savedCheckboxTheme = Platform.MACOS;

        Button loginButton = (operatingSystem == Platform.WINDOWS)
                ? new WindowsButton()
                : new MacButton();

        Checkbox rememberMe = (savedCheckboxTheme == Platform.WINDOWS)
                ? new WindowsCheckbox()
                : new MacCheckbox();

        System.out.println(loginButton.appearance()
                + " + " + rememberMe.appearance());
    }
}
~~~

Kết quả:

~~~text
WindowsButton + MacCheckbox
~~~

Ở ví dụ này, Button được chọn theo hệ điều hành, còn Checkbox được chọn theo một cấu hình giao diện đã lưu. **Cả hai phép khởi tạo đều hợp lệ về kiểu**, nhưng màn hình lại sai yêu cầu về phong cách. Trình biên dịch Java không tự biết rằng hai đối tượng phải thuộc cùng một họ.

Nếu hai nhánh cùng dùng biến `platform` thì lỗi trên chưa xuất hiện ngay. Tuy nhiên, mỗi màn hình vẫn phải lặp lại quy tắc chọn họ, và một lần sửa thiếu ở bất kỳ nơi nào có thể tạo ra lỗi tương tự. Đó mới là rủi ro thiết kế cần giải quyết.

## 4. Vì sao vấn đề nghiêm trọng hơn khi ứng dụng phát triển?

Giả sử ứng dụng có thêm các màn hình Cài đặt, Hồ sơ và Thanh toán. Mỗi màn hình có Button, Checkbox và sau này là TextField. Nhóm phát triển còn nhận yêu cầu hỗ trợ Linux.

Với cách khởi tạo trực tiếp, các thay đổi có thể lan tới nhiều vị trí:

| Thay đổi trong yêu cầu | Điều phải xem lại nếu điều kiện tạo đối tượng nằm rải rác | Rủi ro |
| --- | --- | --- |
| Thêm Linux | Từng chỗ chọn Button, Checkbox, TextField | Chỗ này dùng Linux, chỗ khác rơi vào nhánh mặc định macOS |
| Thêm Checkbox vào màn hình mới | Đoạn mã chọn biến thể Checkbox | Chọn khác họ với Button đã có |
| Sửa cách chọn phong cách | Nhiều đoạn `if`/`switch` ở các màn hình | Quy tắc bị áp dụng không đồng đều |
| Kiểm thử giao diện | Từng tổ hợp thành phần và nền tảng | Dễ bỏ sót tổ hợp trộn họ |

Có ba dấu hiệu kỹ thuật đáng chú ý:

**Mã sử dụng phụ thuộc vào các lớp cụ thể.** Màn hình đăng nhập biết trực tiếp `WindowsButton`, `MacButton`, `WindowsCheckbox` và `MacCheckbox`, dù công việc chính của màn hình chỉ là hiển thị và xử lý đăng nhập. Khi thêm một họ mới, mã sử dụng có thể phải sửa theo.

**Quy tắc chọn họ bị lặp.** Mỗi nơi có thể tự viết một điều kiện chọn theo nền tảng. Số vị trí cần kiểm tra tăng khi số màn hình và loại thành phần tăng. Không có một điểm chịu trách nhiệm duy nhất về việc cung cấp bộ đối tượng cùng phong cách.

**Tính tương thích giữa các đối tượng không được biểu diễn rõ.** Kiểu `Button` cho biết nút có thể làm gì; kiểu `Checkbox` cho biết ô chọn có thể làm gì. Hai kiểu đó không tự nói rằng các phiên bản cụ thể được tạo cho cùng Windows hoặc cùng macOS.

Vấn đề nằm ở **cách phối hợp việc tạo nhiều đối tượng liên quan**, chứ không phải ở thuật toán xử lý thao tác nhấn nút hay kiểm tra trạng thái Checkbox.

## 5. Xác định đúng yêu cầu trước khi chọn mẫu thiết kế

Trước khi chọn một giải pháp, hãy diễn đạt bài toán thành các yêu cầu có thể kiểm chứng.

### Yêu cầu chức năng

- Ứng dụng chọn một nền tảng giao diện đang hoạt động, chẳng hạn Windows hoặc macOS.
- Màn hình cần lấy được Button và Checkbox thông qua các giao diện sử dụng chung.
- Các thành phần được tạo cho **cùng một màn hình** phải thuộc **cùng họ đã chọn**.
- Khi bổ sung một họ Linux, ứng dụng phải có khả năng cung cấp `LinuxButton` và `LinuxCheckbox` cùng nhau.

### Yêu cầu về thiết kế và bảo trì

- Mã nghiệp vụ của màn hình hạn chế phụ thuộc trực tiếp vào tên lớp của từng nền tảng.
- Quy tắc chọn họ được tập trung để tránh mỗi nơi quyết định một cách khác nhau.
- Có thể kiểm thử việc chọn bộ thành phần một cách độc lập với logic đăng nhập.
- Khi mở rộng thêm loại sản phẩm như TextField, vị trí chịu trách nhiệm cung cấp sản phẩm cho mỗi họ phải được xác định rõ.

### Một bộ kiểm thử chấp nhận tối thiểu

| Đầu vào | Thành phần mong đợi | Kết luận |
| --- | --- | --- |
| Chọn Windows | `WindowsButton` và `WindowsCheckbox` | Đạt |
| Chọn macOS | `MacButton` và `MacCheckbox` | Đạt |
| Chọn Windows | `WindowsButton` và `MacCheckbox` | Không đạt |
| Chọn macOS | `MacButton` và `WindowsCheckbox` | Không đạt |
| Thêm Linux hợp lệ | `LinuxButton` và `LinuxCheckbox` | Đạt sau khi hỗ trợ họ Linux |

Kiểm thử giao diện thực tế còn cần xác minh chức năng, khả năng truy cập (*accessibility*), hiển thị khi focus/disabled và các quy ước riêng của hệ điều hành. Bảng trên cô lập đúng **yêu cầu tạo các đối tượng tương thích** mà bài học đang xem xét.

## 6. Nhu cầu dẫn tới Abstract Factory

Nhóm phát triển cần một đối tượng đóng vai trò **bộ tạo thành phần theo họ**. Thay vì để màn hình tự quyết định từng lớp, ứng dụng chọn một bộ tạo phù hợp với nền tảng, rồi yêu cầu bộ tạo ấy cung cấp các loại sản phẩm cần dùng.

~~~mermaid
flowchart TD
    A["Ứng dụng chọn nền tảng"] --> B{"Họ giao diện"}
    B -->|Windows| W["Bộ tạo họ Windows"]
    B -->|macOS| M["Bộ tạo họ macOS"]
    W --> WB["WindowsButton"]
    W --> WC["WindowsCheckbox"]
    M --> MB["MacButton"]
    M --> MC["MacCheckbox"]
~~~

Cả hai bộ tạo đều có thể tuân theo cùng một hợp đồng khởi tạo:

~~~java
interface WidgetFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Khi đó, mã màn hình có thể diễn đạt nhu cầu theo các giao diện chung:

~~~java
// selectFactory là bước chọn bộ tạo theo nền tảng, được minh họa ở mức ý tưởng.
WidgetFactory factory = selectFactory(platform);

Button loginButton = factory.createButton();
Checkbox rememberMe = factory.createCheckbox();
~~~

Đoạn mã này chỉ phác họa **ranh giới trách nhiệm cần có**, chưa phải cách triển khai đầy đủ. Điểm cần quan sát là màn hình không tự chọn `WindowsButton` hay `MacCheckbox`. Một bộ tạo cụ thể chịu trách nhiệm cung cấp các sản phẩm tương ứng với họ của nó.

Đây chính là nhu cầu mà mẫu thiết kế **Abstract Factory** trong nhóm *Creational Design Patterns* giải quyết: **cung cấp một giao diện để tạo các họ đối tượng có liên quan hoặc phụ thuộc lẫn nhau, mà mã sử dụng không cần phụ thuộc vào những lớp cụ thể**.

Trong ví dụ:

| Vai trò trong bài toán | Đối tượng tương ứng |
| --- | --- |
| Sản phẩm trừu tượng | `Button`, `Checkbox` |
| Các sản phẩm cụ thể | `WindowsButton`, `WindowsCheckbox`, `MacButton`, `MacCheckbox` |
| Bộ tạo trừu tượng | `WidgetFactory` với `createButton()` và `createCheckbox()` |
| Các bộ tạo cụ thể dự kiến | Bộ tạo Windows và bộ tạo macOS |
| Mã sử dụng (*client*) | Màn hình đăng nhập, Cài đặt, Hồ sơ… |

Một quy ước quan trọng vẫn phải được giữ: **một màn hình dùng nhất quán cùng một bộ tạo đã chọn**. Abstract Factory tập trung việc tạo từng họ, nhưng nếu mã sử dụng cố tình lấy Button từ bộ tạo Windows và Checkbox từ bộ tạo macOS thì vẫn có thể phá vỡ quy tắc. Giải pháp phát huy tác dụng khi cách cấp phát và sử dụng bộ tạo cũng tuân theo kiến trúc đã chọn.

## 7. Khi nào thực sự cần cách tiếp cận này?

Không phải mọi giao diện có Button và Checkbox đều cần Abstract Factory. Hãy kiểm tra bản chất thay đổi:

| Tình huống | Nhận định |
| --- | --- |
| Chỉ có một loại Button với vài màu thay đổi bằng thuộc tính | Thường chỉ cần cấu hình màu, style hoặc theme |
| Chỉ cần chọn một trong nhiều loại Button, không có sản phẩm liên quan khác | Một cơ chế tạo một sản phẩm như Factory Method hoặc hàm tạo riêng có thể đủ |
| Cần đồng thời Button, Checkbox, TextField với các phiên bản Windows/macOS tương thích | Dấu hiệu phù hợp với Abstract Factory |
| Các thành phần được lựa chọn độc lập, không có ràng buộc dùng chung một họ | Chưa có lý do rõ ràng để tạo một bộ tạo theo họ |
| Sắp thêm Linux và muốn các màn hình nhận nguyên bộ thành phần Linux | Nhu cầu quản lý họ sản phẩm càng rõ |

Đặc biệt, nếu sự khác biệt chỉ là **giao diện trực quan có thể điều khiển bằng một hệ thống theme**, dùng theme có thể đơn giản hơn. Abstract Factory có ý nghĩa khi mỗi nền tảng cần **những phiên bản đối tượng cụ thể** với cách khởi tạo hoặc hành vi riêng, và các phiên bản đó phải được dùng theo bộ.

Abstract Factory cũng có một đánh đổi: thêm **một họ mới** thường thuận lợi vì bổ sung một bộ tạo và các sản phẩm cùng họ; nhưng thêm **một loại sản phẩm mới** như `Slider` đòi hỏi cập nhật hợp đồng của bộ tạo và các bộ tạo cụ thể hiện có. Đây là điều cần cân nhắc trước khi quyết định nhóm các sản phẩm nào vào cùng một factory.

## 8. Tự kiểm tra khả năng nhận diện bài toán

**Tình huống A.** Một nhóm đã có màn hình Windows dùng `WindowsButton` và `WindowsCheckbox`. Nhóm thêm màn hình Hồ sơ, trong đó lập trình viên chọn Button theo hệ điều hành nhưng dùng cố định `MacCheckbox` vì sao chép mã từ tính năng cũ.

- Mỗi thành phần có thể hoạt động bình thường không? **Có.**
- Màn hình có thỏa yêu cầu phong cách không? **Không**, vì hai sản phẩm khác họ.
- Lỗi nằm chủ yếu ở thao tác Checkbox hay cơ chế chọn đối tượng? **Ở cơ chế chọn và phối hợp tạo đối tượng.**

**Tình huống B.** Ứng dụng bổ sung Linux với `LinuxButton` và `LinuxCheckbox`. Mã tạo đối tượng đang được viết trực tiếp trong 15 màn hình.

- Những đoạn mã nào có nguy cơ phải sửa? Các nơi quyết định tạo Button và Checkbox theo nền tảng.
- Làm thế nào giảm nguy cơ bỏ sót? Tập trung lựa chọn **một bộ tạo cho họ Linux**, để mỗi màn hình yêu cầu các loại sản phẩm qua cùng hợp đồng.

**Tình huống C.** Ứng dụng chỉ đổi từ theme sáng sang theme tối; Button và Checkbox vẫn dùng nguyên lớp và nguyên hành vi, chỉ thay màu sắc.

- Có bắt buộc dùng Abstract Factory không? **Không.** Một hệ thống theme hoặc stylesheet có thể giải quyết trực tiếp và ít phức tạp hơn.

### Câu hỏi ghi nhớ

1. Vì sao hai đối tượng đều đúng kiểu `Button` và `Checkbox` nhưng giao diện vẫn có thể sai?
2. Hai chiều biến thể của bài toán là gì? Hãy tự vẽ ma trận khi thêm TextField và Linux.
3. Khi thêm một nền tảng mới, vì sao các nhánh `if`/`switch` nằm rải rác làm tăng rủi ro?
4. Phần nào của việc tạo đối tượng nên được chuyển ra khỏi màn hình đăng nhập?
5. Điều gì khác nhau giữa “chọn một loại Button” và “chọn một họ Button + Checkbox tương thích”?

Nếu có thể xác định rõ **họ sản phẩm**, **các loại sản phẩm trong mỗi họ** và **ràng buộc phải dùng chúng nhất quán**, bạn đã nhận diện được động lực cốt lõi của Abstract Factory trong bài toán giao diện đa nền tảng.
