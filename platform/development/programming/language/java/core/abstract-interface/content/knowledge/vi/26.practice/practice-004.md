# Giải quyết bài toán hình thoi (diamond problem) với nhiều interface

Trong Java, một lớp chỉ có thể `extends` một lớp cha, nhưng có thể `implements` nhiều interface. Điều này cho phép một đối tượng có nhiều vai trò và nhiều hợp đồng kiểu. Tuy nhiên, khi các interface tạo thành một đồ thị kế thừa hình thoi và mỗi nhánh cung cấp một `default method` cùng chữ ký nhưng khác cách thực hiện, lớp ở đáy hình thoi phải quyết định hành vi nào là đúng.

Đó là **diamond problem** (bài toán hình thoi). Java cho phép đa kế thừa kiểu qua interface nhưng không tự chọn tùy tiện giữa hai default method xung đột. Trình biên dịch yêu cầu lớp giải quyết sự mơ hồ ngay tại thời điểm biên dịch.

## 1. Nhận diện cấu trúc hình thoi

Xét một thiết bị vừa có vai trò kết nối mạng, vừa có vai trò lưu trữ:

~~~text
                 Device
                /      \
       NetworkDevice   StorageDevice
                \      /
                SmartDevice
~~~

- `Device` là interface chung.
- `NetworkDevice` và `StorageDevice` đều kế thừa `Device`.
- `SmartDevice` implements cả hai nhánh để cung cấp hai vai trò cho cùng một đối tượng.

Nếu `Device` khai báo một default method tên `status()`, cả hai nhánh có thể kế thừa phương thức đó. Khi đó chúng đang cùng dùng một implementation gốc, nên không có hai cách thực hiện khác nhau để lựa chọn. Tình huống xung đột thực sự xuất hiện khi mỗi nhánh **ghi đè** `status()` với ý nghĩa riêng:

~~~java
interface NetworkDevice extends Device {
    @Override
    default String status() {
        return "network";
    }
}

interface StorageDevice extends Device {
    @Override
    default String status() {
        return "storage";
    }
}
~~~

Nếu `SmartDevice` implements cả `NetworkDevice` và `StorageDevice` mà không ghi đè `status()`, Java không biết cần kế thừa implementation nào. Kết quả là lỗi biên dịch, không phải một lựa chọn ngẫu nhiên khi chạy chương trình.

## 2. Quy tắc Java dùng để giải quyết xung đột

Khi nhiều interface cung cấp phương thức có cùng chữ ký, xét theo thứ tự sau:

1. **Phương thức instance cụ thể của lớp có ưu tiên hơn default method của interface.** Nếu lớp cha là một class có phương thức cụ thể phù hợp, phương thức đó được ưu tiên theo quy tắc phân giải của Java.
2. **Interface cụ thể hơn có ưu tiên hơn interface cha.** Nếu một interface con ghi đè default method của interface cha, lớp triển khai interface con sẽ nhận phiên bản cụ thể hơn, miễn là không có xung đột khác giữa các nhánh không liên quan.
3. **Hai default method xung đột từ các interface không có quan hệ kế thừa cụ thể phải được lớp triển khai ghi đè.** Lớp có thể tự định nghĩa hành vi mới hoặc chủ động gọi các implementation mong muốn bằng cú pháp `InterfaceName.super.method()`.
4. **Các phương thức abstract trùng chữ ký thường có thể được triển khai bằng một phương thức duy nhất.** Nếu các khai báo không tương thích, chẳng hạn kiểu trả về không thể thỏa mãn đồng thời, chương trình sẽ không biên dịch.
5. **Không dựa vào thứ tự liệt kê interface trong `implements`.** Đổi thứ tự `implements A, B` thành `implements B, A` không phải cách giải quyết xung đột.

Cần phân biệt hai trường hợp: cùng kế thừa một default method từ một interface tổ tiên không nhất thiết gây mơ hồ; hai nhánh ghi đè phương thức đó bằng các implementation khác nhau mới tạo xung đột cần giải quyết.

## 3. Cách viết lớp giải quyết xung đột

Có hai lựa chọn phổ biến:

- **Tự định nghĩa lại hành vi** khi lớp kết hợp có quy tắc riêng. Đây thường là lựa chọn rõ nhất nếu hành vi của đối tượng không đơn giản là một trong hai nhánh.
- **Gọi rõ implementation của từng interface** bằng `NetworkDevice.super.status()` hoặc `StorageDevice.super.status()` khi muốn tái sử dụng logic đã có.

Cú pháp `InterfaceName.super.method()` chỉ dùng để gọi default method từ interface trực tiếp mà lớp triển khai. Trong ví dụ, `NetworkDevice` và `StorageDevice` là các interface trực tiếp của `SmartDevice`, nên các lời gọi đó hợp lệ. Không thể dùng `Device.super.status()` ở đây để bỏ qua các nhánh trung gian, vì `Device` không phải interface trực tiếp được `SmartDevice` triển khai.

Không bắt buộc phải kết hợp cả hai implementation. Lớp có thể trả về một trạng thái tổng hợp, chọn một nhánh theo quy tắc nghiệp vụ, hoặc cung cấp một định nghĩa mới — miễn là quyết định đó rõ ràng và phù hợp với hợp đồng công khai.

## 4. Ví dụ Java hoàn chỉnh, có thể chạy

Lưu toàn bộ mã sau vào file `InterfaceDiamondDemo.java`. Ví dụ dùng ba interface và một lớp triển khai cả hai nhánh. `SmartDevice` giải quyết xung đột `status()` bằng cách gọi tường minh default method của từng interface; đồng thời nó cung cấp các phương thức abstract về mã mạng và dung lượng lưu trữ.

~~~java
import java.util.Objects;

interface Device {
    default String status() {
        return "generic";
    }
}

interface NetworkDevice extends Device {
    @Override
    default String status() {
        return "network";
    }

    String networkId();
}

interface StorageDevice extends Device {
    @Override
    default String status() {
        return "storage";
    }

    long capacityGb();
}

final class SmartDevice implements NetworkDevice, StorageDevice {
    private final String networkId;
    private final long capacityGb;

    SmartDevice(String networkId, long capacityGb) {
        this.networkId = Objects.requireNonNull(networkId, "networkId");
        if (capacityGb <= 0) {
            throw new IllegalArgumentException("capacityGb must be positive");
        }
        this.capacityGb = capacityGb;
    }

    @Override
    public String status() {
        return NetworkDevice.super.status() + "+" + StorageDevice.super.status();
    }

    @Override
    public String networkId() {
        return networkId;
    }

    @Override
    public long capacityGb() {
        return capacityGb;
    }
}

public class InterfaceDiamondDemo {
    public static void main(String[] args) {
        SmartDevice smart = new SmartDevice("net-7", 512);

        Device device = smart;
        NetworkDevice network = smart;
        StorageDevice storage = smart;

        System.out.println("status=" + device.status());
        System.out.println("networkId=" + network.networkId());
        System.out.println("capacityGb=" + storage.capacityGb());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac InterfaceDiamondDemo.java
java InterfaceDiamondDemo
~~~

Output chính xác:

~~~text
status=network+storage
networkId=net-7
capacityGb=512
~~~

### Đọc kết quả

- Biến `device` có kiểu tham chiếu `Device`, nhưng đối tượng thực tế là `SmartDevice`. Lời gọi `device.status()` dispatch tới phương thức ghi đè trong `SmartDevice`, nên kết quả là `network+storage`.
- Biến `network` có kiểu tham chiếu `NetworkDevice`; nó có thể gọi `networkId()`, vì phương thức đó thuộc hợp đồng của interface này.
- Biến `storage` có kiểu tham chiếu `StorageDevice`; nó có thể gọi `capacityGb()`.
- Cùng một đối tượng thực hiện nhiều interface mà không cần đa kế thừa class. Mỗi interface thể hiện một vai trò, còn lớp cụ thể kết hợp các vai trò đó.

Constructor cũng kiểm tra dữ liệu đầu vào: mã mạng không được null và dung lượng phải dương. Những kiểm tra này là quy tắc của đối tượng, không phải cơ chế giải quyết diamond problem, nhưng chúng minh họa nơi lớp cụ thể chịu trách nhiệm bảo vệ invariant.

## 5. Thấy lỗi trước khi sửa

Nếu bỏ phần ghi đè `status()` khỏi `SmartDevice`, đồng thời giữ nguyên việc triển khai `networkId()` và `capacityGb()`, cấu trúc sau sẽ không biên dịch:

~~~java
final class AmbiguousDevice implements NetworkDevice, StorageDevice {
    @Override
    public String networkId() {
        return "net-7";
    }

    @Override
    public long capacityGb() {
        return 512;
    }

    // Thiếu override status():
    // hai default method không liên quan cùng cung cấp status().
}
~~~

Trình biên dịch báo rằng lớp kế thừa các default method không liên quan có cùng chữ ký `status()`. Cách sửa không phải ép kiểu đối tượng ở nơi gọi, đổi thứ tự interface hoặc chọn bằng `if/else` bên ngoài. Cần định nghĩa rõ `status()` ngay trong lớp triển khai (hoặc thiết kế lại các interface nếu hai hợp đồng vốn không nên xung đột).

## 6. Các trường hợp liên quan cần phân biệt

### Interface con ghi đè interface cha

Nếu `FastNetworkDevice` extends `NetworkDevice` và ghi đè `status()`, implementation của interface con cụ thể hơn implementation kế thừa từ `NetworkDevice`. Khi một lớp chỉ nhận các đường kế thừa không xung đột, Java ưu tiên phương thức từ interface cụ thể hơn.

### Lớp cha đã có phương thức cụ thể

Nếu lớp triển khai extends một class có phương thức instance cụ thể phù hợp với chữ ký, phương thức của class được ưu tiên hơn default method. Điều này giúp default method của interface không tự ý thay thế hành vi đã có của lớp cha.

### Hai interface chỉ khai báo cùng phương thức abstract

Nếu hai interface cùng khai báo một phương thức abstract tương thích, lớp thường chỉ cần triển khai một lần để đáp ứng cả hai hợp đồng. Không có hai default implementation cạnh tranh để lựa chọn. Tuy vậy, kiểu trả về, visibility và các điều kiện của chữ ký vẫn phải hợp lệ theo Java.

### Phương thức static của interface

Phương thức static thuộc interface khai báo nó và được gọi bằng tên interface, ví dụ `Device.someUtility()` nếu phương thức đó được khai báo trong `Device`. Không xử lý xung đột static method như xung đột default method; static method không được kế thừa và override theo cơ chế đa hình instance.

## 7. Lỗi thường gặp và cách tránh

- **Cho rằng Java cấm nhiều interface:** Java cho phép một lớp implements nhiều interface. Giới hạn một lớp cha áp dụng cho kế thừa class, không phải số interface.
- **Cho rằng mọi hình thoi đều lỗi:** nếu các nhánh cùng kế thừa một implementation gốc mà không ghi đè khác nhau, không nhất thiết có xung đột.
- **Quên override khi hai default method khác nhau:** lỗi xuất hiện ở thời điểm biên dịch. Giải quyết tại lớp kết hợp để hành vi trở nên minh bạch.
- **Gọi `Device.super.status()` từ lớp không implements trực tiếp `Device`:** hãy gọi default method qua interface trực tiếp phù hợp, hoặc tự viết hành vi kết hợp.
- **Dùng nhiều interface chỉ để tạo hình thoi:** cấu trúc kế thừa không tự tạo ra giá trị. Mỗi interface nên đại diện cho một hợp đồng hoặc vai trò có ý nghĩa, chẳng hạn khả năng kết nối và khả năng lưu trữ.
- **Đặt cùng tên phương thức cho hai ý nghĩa khác nhau:** nếu hai interface dùng `status()` với ngữ nghĩa không tương thích, cân nhắc đổi tên, tách trách nhiệm hoặc dùng adapter thay vì bắt mọi lớp kết hợp phải giải quyết cùng một xung đột.
- **Dùng default method cho trạng thái đối tượng:** interface không mang trạng thái instance như class. Dữ liệu riêng của đối tượng nên được giữ trong lớp triển khai hoặc collaborator phù hợp.

## 8. Nguyên tắc thiết kế khi có nhiều interface

Mỗi interface nên mô tả một hợp đồng rõ ràng và có mức độ kết dính cao. Một lớp có thể triển khai nhiều interface để kết hợp các khả năng độc lập, nhưng không nên chia nhỏ một cách máy móc chỉ để đạt số lượng interface lớn.

Khi thiết kế API có default method, hãy chọn tên và ngữ nghĩa đủ đặc thù, cân nhắc ảnh hưởng khi các interface được kết hợp, và ghi đè tường minh nếu các default method có thể xung đột. Với lớp triển khai, hãy quyết định hành vi tổng hợp ở một nơi thay vì để client tự lựa chọn hoặc ép kiểu theo từng nhánh.

**Tóm lại:** Java hỗ trợ đa kế thừa kiểu thông qua interface nhưng buộc phải làm rõ hành vi khi nhiều default method không tương thích cùng xuất hiện. Xác định nhánh nào sở hữu hợp đồng, hiểu quy tắc ưu tiên của Java, rồi ghi đè trong lớp kết hợp hoặc gọi rõ implementation bằng `InterfaceName.super.method()`.
