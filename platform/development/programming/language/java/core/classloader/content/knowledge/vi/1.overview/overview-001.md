# Class loader là gì và vì sao JVM cần nạp lớp động?

Trong Java, mã nguồn được biên dịch thành bytecode, nhưng bytecode không tự trở thành mã đang chạy. **Class loader (bộ nạp lớp)** là thành phần tham gia tìm và đưa định nghĩa lớp từ bytecode vào JVM, để JVM có thể liên kết, khởi tạo và sử dụng lớp đó khi cần. Cơ chế này giúp một chương trình sử dụng thư viện, driver hoặc thành phần mở rộng tại thời điểm chạy mà không phải nạp trước mọi lớp có thể tồn tại.

## 1. Hiểu đúng khái niệm

Một lớp Java thường đi qua các hình thức sau:

~~~text
Mã nguồn .java
    │ javac
    ▼
Bytecode .class (có thể nằm trong JAR, module, thư mục hoặc nguồn sinh động)
    │ class loader tìm/đọc/định nghĩa lớp
    ▼
Class<?> trong JVM
    │ liên kết, rồi khởi tạo tại thời điểm thích hợp
    ▼
Đối tượng, phương thức, trường tĩnh và hành vi chương trình
~~~

- **Lớp trên đĩa** là một biểu diễn bytecode; một tệp JAR có thể chứa hàng trăm hoặc hàng nghìn tệp .class.
- **Lớp đã được nạp** là một định nghĩa được JVM nhận biết, biểu diễn trong Java bằng một đối tượng Class<?>. Nạp một lớp không đồng nghĩa tạo một instance của lớp ấy.
- **Class loader** là cơ chế tìm kiếm và định nghĩa lớp. Với các class loader dựa trên java.lang.ClassLoader, việc nạp có thể bắt đầu qua loadClass(...), hoặc gián tiếp khi JVM cần một loại chưa có.
- **Nạp động** nghĩa là JVM có thể phát hiện/nạp định nghĩa lớp trong quá trình thực thi. Điều đó không có nghĩa Java luôn biên dịch mã nguồn .java vào lúc chạy, cũng không có nghĩa mọi lớp đều được nạp theo cách lười biếng tuyệt đối.

Ví dụ: ứng dụng biết trước interface của một driver. Khi chạy, nó mới tìm được thư viện chứa lớp triển khai thực tế, nhờ cấu hình và cơ chế nạp lớp. Mã gọi sử dụng interface chung, không cần tự viết lại mỗi khi có nhà cung cấp mới.

## 2. Vì sao JVM cần cơ chế nạp lớp động?

**Thứ nhất, chương trình Java có hệ sinh thái thư viện thay đổi theo triển khai.** Cùng một ứng dụng có thể chạy với tập JAR/module khác nhau. JVM phải có cách tìm bytecode tương ứng với tên lớp tại môi trường chạy hiện tại.

**Thứ hai, ứng dụng có thể phát hiện thành phần lúc chạy.** Driver cơ sở dữ liệu, plugin, bộ mã hóa, bộ ghi log hoặc nhà cung cấp dịch vụ có thể được chọn qua cấu hình hay Service Provider Interface (SPI), thay vì cố định một lớp triển khai trong mã nguồn.

**Thứ ba, không phải mọi lớp đều cần được xử lý ngay từ đầu.** Một chương trình chỉ dùng một nhánh chức năng có thể không cần nạp các lớp ở nhánh khác. JVM được quyền chủ động nạp hoặc liên kết sớm hơn khi phù hợp, nhưng phải bảo đảm các quy tắc quan sát được về khởi tạo lớp.

**Thứ tư, các môi trường chạy cần tổ chức không gian tên.** Application server, hệ plugin hoặc công cụ triển khai có thể dùng nhiều class loader để phân tách các tập lớp, chẳng hạn phục vụ các ứng dụng hoặc phiên bản thư viện khác nhau. Phân tách này cần thiết nhưng không tự bảo đảm an ninh.

**Thứ năm, bytecode không nhất thiết có sẵn thành tệp .class trên đĩa.** Một framework hoặc thư viện có thể tạo bytecode trong bộ nhớ rồi nhờ class loader định nghĩa lớp. Khả năng đó hỗ trợ proxy, mã được tạo và các cơ chế mở rộng khác.

Nói cách khác, class loading tách **thời điểm biên dịch**, **nguồn chứa định nghĩa lớp**, **thời điểm JVM cần lớp** và **class loader sở hữu định nghĩa** thành các mối quan tâm riêng.

## 3. JVM làm gì khi cần một lớp?

Khi chương trình tham chiếu tới một kiểu, JVM phải bảo đảm có định nghĩa lớp phù hợp; sau đó kiểu có thể được liên kết và khởi tạo theo quy tắc Java. Ba mốc này khác nhau:

| Mốc | Câu hỏi cần trả lời |
| --- | --- |
| **Loading** | Bộ nạp nào tìm và định nghĩa lớp từ bytecode? |
| **Linking** | Bytecode đã được kiểm tra (*verification*), trường tĩnh được chuẩn bị (*preparation*) và những tham chiếu cần thiết được phân giải (*resolution*) ra sao? |
| **Initialization** | Khi nào JVM thực thi logic khởi tạo `static` của lớp? |

JVM có thể phân giải một số tham chiếu muộn; việc nạp lớp không tự chạy `static {}` hoặc tạo instance. Chẳng hạn, `Class.forName(name, false, loader)` yêu cầu tìm lớp mà không yêu cầu khởi tạo; gọi phương thức `static` của lớp chưa khởi tạo thường làm phát sinh bước initialization.

Để quan sát cụ thể, xem thí nghiệm ở mục 6. Khi phân tích edge case về `ConstantValue`, thứ tự khởi tạo superclass hoặc lỗi liên kết, cần xét chi tiết từng giai đoạn thay vì suy đoán từ một dòng log class loading.

## 4. Ai nạp lớp? Mô hình class loader của Java hiện đại

Trên JDK phổ biến từ Java 9 trở lên, ba nhóm bộ nạp thường gặp là:

| Bộ nạp | Phạm vi điển hình | Dấu hiệu nhận biết |
| --- | --- | --- |
| **Bootstrap loader** | Các lớp nền tảng thiết yếu, chẳng hạn java.lang.Object. | Java API thường biểu diễn loader này bằng null khi gọi Class.getClassLoader(). |
| **Platform class loader** | Nhiều module nền tảng của JDK. | Truy cập bằng ClassLoader.getPlatformClassLoader(). |
| **Application/System class loader** | Lớp ứng dụng và thư viện trên classpath/module path mà bộ nạp này phụ trách. | Truy cập bằng ClassLoader.getSystemClassLoader() trong ứng dụng thông thường. |

Mô hình ủy quyền mặc định thường được vẽ:

~~~text
Yêu cầu nạp một tên lớp
        │
        ▼
Application loader
        │ hỏi parent trước
        ▼
Platform loader
        │ hỏi parent trước
        ▼
Bootstrap loader
        │
        ├── tìm thấy → dùng định nghĩa lớp đã có/được nạp
        └── không thấy → trả quyền thử lại cho các loader bên dưới
~~~

Đây là **parent delegation**: class loader con kiểm tra lớp đã nạp, thường nhờ cha thử nạp trước, rồi mới tự tìm/định nghĩa nếu cha không tìm được. Nhờ đó, mã ứng dụng thông thường không thể thay thế java.lang.String bằng một lớp tùy ý có cùng tên trên classpath. Không phải mọi custom loader đều giữ chính sách parent-first: có thiết kế child-first có kiểm soát cho plugin hoặc container.

Trong mô hình module Java từ Java 9, cách tìm lớp còn chịu ảnh hưởng của module graph, khả năng đọc module, exports/opens và cấu hình loader. Sơ đồ trên là mô hình tư duy căn bản, không phải danh sách đầy đủ mọi luật tìm lớp của mọi JVM.

**Lưu ý quan trọng:** Parent của một ClassLoader có thể là null khi cha là bootstrap; điều đó không nói rằng lớp không có class loader theo nghĩa vận hành. Đừng giả định tên triển khai nội bộ của loader luôn giống nhau giữa các bản JDK.

## 5. Định danh lớp phụ thuộc cả tên lẫn class loader

Một tên nhị phân như `com.example.Plugin` **chưa đủ** để kết luận hai đối tượng thuộc cùng kiểu: identity của lớp tham chiếu trong JVM còn phụ thuộc **defining loader**. Nếu loader A và B tự định nghĩa hai bản `com.example.Plugin`, JVM coi đó là hai kiểu khác nhau; cast trực tiếp có thể thất bại.

Ngược lại, hai loader cùng ủy quyền cho một loader cha có thể nhận lại **cùng** `Class<?>`. Loader gọi `loadClass` (*initiating loader*) vì thế không nhất thiết là loader đã định nghĩa lớp mà `Class.getClassLoader()` trả về. Trong hệ plugin, host và plugin nên chia sẻ một định nghĩa của API/SPI, còn các implementation có thể do loader riêng quản lý.

Đây là nền tảng để hiểu class identity và khả năng trao đổi dữ liệu giữa các plugin; ví dụ ở phần tiếp theo tập trung vào **nạp so với khởi tạo**, không giả lập hai loader độc lập.

## 6. Ví dụ Java 17+: nạp lớp chưa đồng nghĩa khởi tạo

Tạo tệp **ClassLoaderOverview.java** với toàn bộ nội dung sau:

~~~java
public class ClassLoaderOverview {
    static class Greeter {
        static {
            System.out.println("[init] Greeter");
        }

        static void greet() {
            System.out.println("Hello from Greeter");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader loader = ClassLoaderOverview.class.getClassLoader();

        Class<?> type = Class.forName(
                "ClassLoaderOverview$Greeter",
                false,
                loader
        );

        System.out.println("Discovered: " + type.getName());
        System.out.println("Before method call");

        Greeter.greet();

        System.out.println("Same class: " + (type == Greeter.class));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac ClassLoaderOverview.java
java ClassLoaderOverview
~~~

Đầu ra:

~~~text
Discovered: ClassLoaderOverview$Greeter
Before method call
[init] Greeter
Hello from Greeter
Same class: true
~~~

**Giải thích theo thứ tự:**

1. Tên nhị phân của lớp lồng Greeter là ClassLoaderOverview$Greeter. Chuỗi được đưa vào Class.forName(..., false, loader), nên JVM thu được đối tượng Class mà chưa phải chạy bộ khởi tạo static của Greeter.
2. Lệnh in Discovered và Before method call chạy trước, chứng minh việc lấy Class<?> không tự kích hoạt đoạn in [init].
3. Greeter.greet() là một lần gọi phương thức static, nên JVM phải khởi tạo Greeter trước khi thực thi thân phương thức. Bộ khởi tạo chạy đúng một lần đối với định nghĩa lớp đó.
4. Biểu thức type == Greeter.class cho true vì cả hai biểu thức tham chiếu tới **cùng định nghĩa lớp**, do cùng loader phù hợp nạp. Kết luận này không mở rộng cho hai bản sao cùng tên do hai defining loader khác nhau định nghĩa.

Nếu đổi thành **Class.forName("ClassLoaderOverview$Greeter")**, lời gọi một tham số thường yêu cầu khởi tạo ngay; dòng [init] có thể xuất hiện trước dòng Discovered. Nếu dùng **loader.loadClass("ClassLoaderOverview$Greeter")**, hành vi loadClass mặc định chỉ yêu cầu nạp, không yêu cầu khởi tạo; class loader tùy biến vẫn phải tuân thủ hợp đồng JVM liên quan.

Không dùng một log duy nhất để suy đoán chính xác thời điểm JVM đọc từng byte .class: JVM có quyền tải, kiểm tra hoặc resolve ở thời điểm khác miễn bảo đảm ngữ nghĩa chương trình.

## 7. Nạp động giúp ứng dụng mở rộng như thế nào?

Một trường hợp thực tế là **SPI với ServiceLoader**:

1. Một thư viện chung khai báo interface, ví dụ Encoder.
2. Một hoặc nhiều thư viện nhà cung cấp có lớp triển khai Encoder, kèm metadata đăng ký provider (ví dụ META-INF/services với classpath, hoặc provides ... with ... trong module).
3. Ứng dụng gọi ServiceLoader.load(Encoder.class), rồi sử dụng các provider được phát hiện. Đây là cơ chế tích hợp được Java cung cấp; API chung và provider phải có khả năng truy cập/hiển thị phù hợp.

Đoạn dưới **chỉ là phác họa ý tưởng**, chưa phải chương trình độc lập vì interface Encoder và metadata provider không được khai báo tại đây:

~~~java
ServiceLoader<Encoder> providers = ServiceLoader.load(Encoder.class);
for (Encoder encoder : providers) {
    encoder.encode();
}
~~~

Ứng dụng có thể thêm một provider hợp lệ khi đóng gói/triển khai mà không sửa vòng lặp. Tuy nhiên, class loading **không tự quét toàn bộ JAR để tìm mọi class**; ServiceLoader tuân theo metadata và quy tắc khám phá của nó. Với tình huống thư viện gọi SPI nhưng provider thuộc loader khác, **thread context class loader** (Thread.currentThread().getContextClassLoader()) có thể giúp thư viện truy cập lớp của ứng dụng. Đây là một cơ chế phối hợp có chủ đích, không đồng nghĩa mọi thư viện nên thay đổi context loader tùy ý.

Ở các hệ plugin nâng cao, ứng dụng còn có thể tạo custom ClassLoader, định nghĩa lớp từ các byte bytecode hợp lệ, và quản lý vòng đời của loader. Các bước đó đi xa hơn câu hỏi tổng quan này; trước khi tự viết loader, nên cân nhắc ServiceLoader, module và cơ chế plugin hiện có.

## 8. Những lỗi dễ nhầm khi gặp class loading

Khi gặp lỗi, trước tiên phân biệt **không tìm được tên lớp**, **không thể sử dụng định nghĩa lớp**, và **hai định nghĩa cùng tên nhưng khác kiểu**:

- `ClassNotFoundException`: API như `loadClass` hoặc `Class.forName` được yêu cầu tìm tên lớp nhưng không tìm/nạp được. Kiểm tra tên nhị phân, loader và JAR/module có thể nhìn thấy.
- `NoClassDefFoundError`: JVM không thể có hoặc sử dụng một lớp đang cần, đôi khi là hậu quả của lần khởi tạo thất bại trước đó. Xem nguyên nhân gốc, không tự động kết luận thiếu JAR.
- `ClassCastException` với tên giống nhau: kiểm tra **hai đối tượng `Class<?>` và defining loader**, thay vì chỉ so sánh `getName()`.
- `LinkageError` hoặc `ExceptionInInitializerError`: lần lượt điều tra sự không tương thích khi định nghĩa/liên kết, hoặc exception từ logic khởi tạo tĩnh.

Có thể quan sát loader bằng `SomeType.class.getClassLoader()` và sự kiện nạp trên HotSpot hiện đại bằng `-Xlog:class+load=info`. Đây là dấu hiệu để điều tra; log loading không phải bằng chứng lớp đã initialized.

## 9. Giới hạn và lưu ý thiết kế

- **Nạp được lớp không có nghĩa được phép truy cập mọi thành viên.** Quy tắc Java access control, module exports/opens và kiểm tra khi liên kết/phản chiếu vẫn áp dụng.
- **Class loader không phải sandbox tin cậy để chạy mã độc.** Verification giúp bảo đảm tính hợp lệ của bytecode, nhưng không có nghĩa mã đã được nạp an toàn về quyền truy cập tài nguyên. Mã không tin cậy cần cơ chế cô lập và chính sách bảo mật phù hợp.
- **Thấy tên lớp trong JAR không bảo đảm lớp nạp thành công.** Có thể thiếu dependency, sai phiên bản bytecode so với JVM, mâu thuẫn module hoặc loader không nhìn thấy JAR.
- **Dỡ lớp không đơn giản là xóa tệp JAR hoặc đặt một biến bằng null.** JVM có thể thu hồi metadata lớp khi điều kiện unload đáp ứng, thường liên quan tới việc defining loader và các lớp của nó không còn được giữ sống; thời điểm thu hồi do JVM quyết định. Thread, cache, listener hoặc context class loader giữ tham chiếu có thể ngăn loader được thu gom.
- **Không dùng Class.forName tùy tiện với tên lấy từ input không tin cậy.** Việc nạp/khởi tạo có thể kích hoạt code không mong đợi. Nên giới hạn tên lớp/provider hợp lệ và dùng API công khai của thư viện khi có thể.

## 10. Tự kiểm tra hiểu bài

**Câu 1.** Chương trình có 200 lớp trong các JAR. Khi khởi động, JVM có bắt buộc khởi tạo cả 200 lớp không?

**Trả lời:** Không. Các lớp được khởi tạo theo quy tắc sử dụng chủ động và các quy tắc liên quan; JVM có quyền nạp/liên kết ở thời điểm thích hợp, nhưng việc JAR có lớp không tự buộc khởi tạo tất cả.

**Câu 2.** Hai class loader định nghĩa cùng một binary name com.example.Task. Có thể ép một object của Task bên loader A thành Task bên loader B không?

**Trả lời:** Không, nếu chúng thực sự là hai định nghĩa khác nhau. Trong JVM, identity của kiểu gắn với tên nhị phân **và defining loader**; cần chia sẻ một hợp đồng kiểu được nạp chung khi các module trao đổi object.

**Câu 3.** Vì sao Class.forName(name, false, loader) có thể trả Class<?> nhưng khối static vẫn chưa chạy?

**Trả lời:** Vì loading/linking và initialization là các giai đoạn khác nhau. Tham số false chỉ ra rằng lời gọi đó không yêu cầu initialization; lần sử dụng chủ động về sau mới buộc khởi tạo, nếu chưa khởi tạo.

## Ghi nhớ

**Class loader giúp JVM nhận biết các định nghĩa lớp tại thời điểm chạy.** Nhờ nạp lớp động, Java có thể dùng thư viện và provider được quyết định khi triển khai, triển khai plugin và phân tách một phần không gian kiểu. Để hiểu chính xác hành vi, luôn tách ba ý: **nạp lớp ≠ khởi tạo lớp**, **tên lớp ≠ định danh kiểu đầy đủ**, và **khả năng tìm thấy lớp ≠ khả năng dùng lớp an toàn/hợp lệ**.
