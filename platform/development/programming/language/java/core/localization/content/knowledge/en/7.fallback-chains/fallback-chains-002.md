# Quan hệ tài nguyên con với bundle cha trong Java ResourceBundle

## 1. Vì sao một bundle con có thể dùng tài nguyên từ bundle cha?

Trong ứng dụng Java hỗ trợ nhiều ngôn ngữ, một số nội dung giống nhau giữa các biến thể locale. Chẳng hạn, giao diện tiếng Việt chung và giao diện tiếng Việt tại Việt Nam đều dùng phần lớn nhãn giống nhau; bản Việt Nam chỉ cần sửa vài cách diễn đạt. Nếu sao chép toàn bộ thông điệp vào từng tệp, các bản dịch dễ lệch nhau và khó bảo trì.

**`ResourceBundle` hỗ trợ quan hệ cha–con (parent chain)** để một bundle chuyên biệt có thể:

- **Ghi đè** giá trị của khóa đã có trong bundle chung.
- **Kế thừa** giá trị của khóa chưa định nghĩa ở bundle con, bằng cách tìm tiếp trong bundle cha.
- **Bổ sung** khóa riêng cho một vùng/ngôn ngữ mà bundle cha không có.

Ví dụ với base name `messages` và locale `vi-VN`, khi có đủ ba tệp resource bundle theo quy ước chuẩn, chuỗi quan hệ là:

~~~text
messages_vi_VN.properties       <- con, cụ thể nhất (tiếng Việt ở Việt Nam)
             |
             v  nếu thiếu khóa trong con
messages_vi.properties          <- cha gần (tiếng Việt)
             |
             v  nếu vẫn thiếu khóa
messages.properties             <- cha gốc (root bundle)
             |
             v  nếu cả chuỗi đều thiếu khóa
MissingResourceException
~~~

**Thứ tự ưu tiên:** tài nguyên ở bundle cụ thể nhất được dùng trước; chỉ khi khóa chưa xuất hiện ở đó mới chuyển sang cha. Quan hệ cha–con áp dụng **theo từng khóa**, nên một màn hình có thể lấy các nhãn từ nhiều tệp khác nhau trong cùng chuỗi.

Đây là một dạng **fallback nội dung**, có thể hoạt động ngay cả khi chính bundle được yêu cầu đã tồn tại. Không cần phải thiếu cả tệp `messages_vi_VN.properties` thì Java mới đọc `messages_vi.properties`.

## 2. Tên bundle quyết định chuỗi ứng viên

`ResourceBundle.getBundle(baseName, locale)` sử dụng base name và các thành phần của `Locale` để tìm họ tài nguyên thích hợp. Với cấu hình thông thường, tệp properties có quy tắc tên:

| Tệp | Phạm vi |
| --- | --- |
| `messages.properties` | Bundle gốc, không gắn locale cụ thể |
| `messages_vi.properties` | Chuyên biệt cho tiếng Việt |
| `messages_vi_VN.properties` | Chuyên biệt cho tiếng Việt ở Việt Nam |
| `messages_en.properties` | Chuyên biệt cho tiếng Anh |
| `messages_en_GB.properties` | Chuyên biệt cho tiếng Anh ở Anh |

Ví dụ Java:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
~~~

Đây là đoạn minh họa cần `import java.util.Locale;` và `import java.util.ResourceBundle;`. Khi các file nằm đúng classpath, Java tạo hoặc lấy từ cache bundle cụ thể nhất tìm được và thiết lập quan hệ với các bundle cha đã tìm thấy.

Trong ứng dụng có package, base name có thể là `com.example.i18n.messages`; khi đó file properties tương ứng nằm dưới đường dẫn classpath `com/example/i18n/messages*.properties`. **Không** dùng tên file có đuôi `.properties` làm base name và không dùng dấu `-` của BCP 47 trực tiếp trong tên file: quy ước tên tài nguyên ở đây là dấu gạch dưới, chẳng hạn `messages_vi_VN.properties`, trong khi `Locale.toLanguageTag()` trả `vi-VN`.

Với `vi-VN` đơn giản và cơ chế tra cứu mặc định, thứ tự ứng viên là `vi_VN` → `vi` → root. Locale có script, variant và trường hợp đặc biệt có thể có **nhiều ứng viên hơn**; ví dụ `zh-Hant-TW` có thể xem xét bundle theo chữ viết và khu vực. Không tự viết hàm cắt chuỗi `locale.toString()` để dựng parent chain khi Java đã cung cấp thuật toán chuẩn.

## 3. Ví dụ đầy đủ: ba tệp, một chương trình Java 17

Đặt **bốn tệp** dưới cùng một thư mục, không khai báo package, rồi chạy lệnh phía dưới. Đừng đặt nhầm tệp properties trong thư mục con nếu base name là `messages`.

**Tệp `messages.properties` — gốc:**

~~~properties
app.name=Sample App
button.save=Save
button.cancel=Cancel
help.text=General help
~~~

**Tệp `messages_vi.properties` — tiếng Việt:**

~~~properties
app.name=Ứng dụng mẫu
button.save=Lưu
~~~

**Tệp `messages_vi_VN.properties` — tiếng Việt tại Việt Nam:**

~~~properties
button.save=Lưu tại Việt Nam
help.text=Hỗ trợ tại Việt Nam
~~~

**Tệp `BundleParentDemo.java`:**

~~~java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.TreeSet;

public class BundleParentDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = ResourceBundle.getBundle("messages", requested);

        System.out.println("bundle locale: " +
                bundle.getLocale().toLanguageTag());
        System.out.println("app.name: " +
                bundle.getString("app.name"));
        System.out.println("button.save: " +
                bundle.getString("button.save"));
        System.out.println("button.cancel: " +
                bundle.getString("button.cancel"));
        System.out.println("help.text: " +
                bundle.getString("help.text"));

        System.out.println("has inherited cancel: " +
                bundle.containsKey("button.cancel"));
        System.out.println("keys: " +
                new TreeSet<>(bundle.keySet()));

        try {
            bundle.getString("missing.key");
        } catch (MissingResourceException e) {
            System.out.println("missing.key: MissingResourceException");
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17+** từ chính thư mục chứa cả bốn tệp:

~~~bash
javac -encoding UTF-8 BundleParentDemo.java
java BundleParentDemo
~~~

**Kết quả dự kiến** khi chạy đúng bốn file trên, không có bundle cùng tên khác chiếm ưu tiên trên classpath:

~~~text
bundle locale: vi-VN
app.name: Ứng dụng mẫu
button.save: Lưu tại Việt Nam
button.cancel: Cancel
help.text: Hỗ trợ tại Việt Nam
has inherited cancel: true
keys: [app.name, button.cancel, button.save, help.text]
missing.key: MissingResourceException
~~~

Cách suy ra từng dòng:

| Khóa | File chứa giá trị được chọn | Lý do |
| --- | --- | --- |
| `app.name` | `messages_vi.properties` | Con `vi_VN` thiếu khóa, cha `vi` có |
| `button.save` | `messages_vi_VN.properties` | Con định nghĩa khóa, ghi đè `vi` và root |
| `button.cancel` | `messages.properties` | Cả `vi_VN` và `vi` đều thiếu, root có |
| `help.text` | `messages_vi_VN.properties` | Con định nghĩa lại giá trị của root |
| `missing.key` | Không có | Không tìm thấy trong toàn bộ chuỗi cha–con |

`bundle.getLocale()` trả locale của **bundle đã được chọn**, ở đây là `vi-VN`; nó **không chỉ ra riêng** `app.name` hay `button.cancel` đến từ tệp nào. `getString(key)` tự lần theo quan hệ cha khi cần.

`bundle.keySet()` bao gồm khóa tìm thấy trên **bundle hiện tại và các bundle cha**. Ở đây dùng `TreeSet` để sắp thứ tự khóa cho đầu ra ổn định; thứ tự duyệt trực tiếp của một `Set` không nên được giả định. `containsKey("button.cancel")` trả `true` ngay cả khi khóa chỉ tồn tại trong root.

## 4. Cơ chế tra cứu: tìm bundle khác với tìm khóa

Có hai bước khác nhau:

### Bước A — Chọn bundle để trả về

`getBundle("messages", requestedLocale)` tạo chuỗi tên ứng viên từ locale. Java cố tìm bundle phù hợp nhất, có thể kiểm tra class-based bundle và properties-based bundle theo thứ tự định nghĩa. Sau đó, đối với các ứng viên còn lại thực sự có tài nguyên, nó nối quan hệ `parent`.

Ví dụ nếu thiếu `messages_vi_VN.properties`, nhưng `messages_vi.properties` có mặt, đối tượng trả về có thể là `messages_vi`, với parent là `messages`. `bundle.getLocale()` lúc đó là `vi`. Nếu cả `vi_VN` và `vi` không có, thuật toán mặc định có thể thử **locale mặc định của JVM** trước khi dùng root, tùy các bundle hiện có; vì vậy không thể khẳng định yêu cầu `vi-VN` sẽ luôn trả root khi không có bản tiếng Việt.

### Bước B — Tìm một khóa bên trong đối tượng đã chọn

`bundle.getObject(key)`/ `getString(key)` bắt đầu ở bundle được chọn:

~~~text
handleGetObject(key) ở bundle hiện tại
      |
      +-- tìm thấy giá trị --> trả về, không đọc cha
      |
      +-- không tìm thấy --> thử parent.getObject(key)
                                  |
                                  +-- tiếp tục đến root
                                  |
                                  +-- không có ở bất kỳ cấp nào
                                      --> MissingResourceException
~~~

Vì vậy:

- **Thiếu file** ở một cấp: Java có thể chọn ứng viên ít chuyên biệt hơn ngay từ bước A.
- **Có file nhưng thiếu key**: Java có thể lấy key từ cha theo bước B.
- **Có key tại con**: giá trị ở con thắng, ngay cả khi cha có key trùng tên.
- **Không có key ở toàn chuỗi**: `getString` ném `MissingResourceException`, không tự trả về tên key và cũng không tự tạo ra bản dịch.

### Nhìn kỹ mối quan hệ “cha”

Trong Java, `ResourceBundle` có trường `parent` ở mức `protected` và phương thức `setParent` dùng khi kết nối các bundle. Với `PropertyResourceBundle`, ứng dụng thông thường **không cần tự gọi `setParent`**; `ResourceBundle.getBundle` thực hiện cấu hình chuỗi trong quá trình tải.

Bundle cha **không phải** một lớp Java bắt buộc phải được `extends` bởi bundle con. Trong ví dụ properties, cả ba là **các tệp tài nguyên độc lập**; quan hệ cha–con được thiết lập theo tên và locale lúc tải. Java cũng hỗ trợ `ListResourceBundle`/class-based bundle, nhưng khái niệm resource parent khác với quan hệ kế thừa `extends` của ngôn ngữ Java.

## 5. Điểm dễ nhầm: các loại fallback khác nhau

| Tình huống | Nguyên nhân | Kết quả hoặc cơ chế |
| --- | --- | --- |
| Thiếu khóa trong bundle `vi_VN` | Chưa ghi đè khóa | Tìm tiếp `vi`, rồi root nếu có |
| Không tồn tại `messages_vi_VN.properties` | Thiếu ứng viên chính xác | Chọn `vi` hoặc ứng viên phù hợp hơn còn tồn tại |
| Không có bundle theo locale yêu cầu | Thiếu toàn bộ nhánh tài nguyên | Mặc định có thể thử locale của JVM rồi root |
| Không có bundle nào cho base name | Không có tài nguyên tải được | `getBundle` ném `MissingResourceException` |
| Có bundle nhưng toàn chuỗi thiếu một key | Thiếu thông điệp | `getString(key)` ném `MissingResourceException` |
| Con có `button.save=` | Khóa tồn tại với chuỗi rỗng | Chuỗi rỗng của con **ghi đè cha**, không fallback |
| Con có giá trị khác phiên bản cha | Ghi đè chủ đích | Giá trị của con được ưu tiên |

**Mấu chốt:** “chuỗi rỗng” khác “không tồn tại key”. Trong file properties, dòng `button.save=` định nghĩa một key với giá trị rỗng. Khi muốn dùng bản dịch của cha, hãy **bỏ hẳn key** ở con thay vì để key với giá trị `""` hoặc khoảng trắng.

Một nguồn nhầm lẫn khác: `ResourceBundle.getBundle("messages")` không truyền locale nên dựa trên **`Locale.getDefault()`**, và hành vi có thể thay đổi nếu một phần khác của chương trình gọi `Locale.setDefault`. Đối với ứng dụng phục vụ nhiều người dùng, nên truyền locale tường minh cho từng request.

## 6. Parent chain không phải “mọi nhánh locale đều kế thừa nhau”

Các nhánh ngôn ngữ khác nhau không tự tạo quan hệ cha–con chỉ vì cùng một base name:

~~~text
                   messages.properties
                     /          \
          messages_vi.properties  messages_en.properties
                  |                      |
   messages_vi_VN.properties   messages_en_GB.properties
~~~

Trong ví dụ đủ các bundle trên, `messages_vi_VN` không lấy key thiếu từ `messages_en_GB`, vì `en_GB` **không phải cha** của `vi_VN`. Root là mức dùng chung, không mặc định chứa tiếng Anh có thể coi là chính sách bản dịch của toàn sản phẩm mà không có chủ ý rõ ràng.

Có một trường hợp cần phân biệt kỹ: khi không tìm thấy bundle phù hợp với requested locale, cơ chế **fallback locale của JVM** có thể khiến Java chọn một nhánh ngôn ngữ khác làm bundle kết quả. Đây là cơ chế **chọn bundle thay thế**, không phải `vi_VN` tự có quan hệ cha với `en_GB`.

Nếu ứng dụng yêu cầu quy tắc “chỉ dùng chuỗi cha trong nhánh ngôn ngữ được yêu cầu, không chọn ngôn ngữ mặc định của máy”, trên **classpath/unnamed module** có thể cân nhắc `ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)` và overload `getBundle` tương ứng. Ví dụ sau là **đoạn minh họa**:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", requestedLocale, control);
~~~

Dù tắt fallback sang **default JVM locale**, root `messages.properties` vẫn có thể là bundle cuối trong chuỗi nếu nó tồn tại. `getNoFallbackControl` không có nghĩa bỏ root hoặc kiểm tra xem đã có bản dịch đúng ngôn ngữ hay chưa. Các overload nhận `ResourceBundle.Control` không được hỗ trợ khi caller nằm trong **named module**; ở mô hình JPMS cần thiết kế cơ chế resource/provider phù hợp, không sao chép máy móc snippet này.

## 7. Thiết kế chiến lược dịch: cha chung và bản chuyên biệt

Một họ resource có thể được tổ chức theo “nội dung chung trước, ngoại lệ sau”:

1. **Root:** toàn bộ khóa bắt buộc, có giá trị fallback được nhóm phát triển chấp nhận và kiểm soát chất lượng.
2. **Bundle theo ngôn ngữ:** các khóa tiếng Việt, tiếng Anh, tiếng Pháp… có nội dung dịch được quản lý rõ ràng.
3. **Bundle theo region/script:** chỉ định nghĩa những cụm từ thực sự khác về vùng hoặc chữ viết, thay vì sao chép nguyên cả bundle ngôn ngữ.

Tuy nhiên, **không nên lạm dụng parent fallback để che việc chưa dịch**. Nếu root đang là tiếng Anh và một bundle tiếng Việt thiếu nhiều khóa, người dùng có thể thấy màn hình trộn tiếng Việt với tiếng Anh. Java vẫn coi đó là chuỗi tra cứu hợp lệ; việc bản dịch có đủ đạt yêu cầu sản phẩm hay không là một quyết định chất lượng riêng.

Đề xuất thực hành:

- Dùng tên khóa ổn định, có ngữ cảnh (`checkout.button.pay`, `order.status.pending`), tránh dùng nguyên câu ngôn ngữ gốc làm khóa.
- Quản lý danh sách khóa bắt buộc và kiểm thử từng bundle theo ngôn ngữ. Đừng dùng `bundle.keySet()` để kết luận mọi khóa đều được dịch ở **bundle con**, vì tập này có thể gồm khóa kế thừa.
- Chỉ tạo bundle vùng/ngôn ngữ khi có khác biệt thực chất; nếu hai locale sử dụng cùng một bản dịch, cha theo ngôn ngữ có thể là nguồn duy nhất.
- Định nghĩa chính sách fallback minh bạch: thiếu nhánh locale nên quay về ngôn ngữ mặc định sản phẩm hay báo không hỗ trợ; thiếu key ở cùng ngôn ngữ có được dùng root hay cần báo lỗi?
- Không đưa dữ liệu nghiệp vụ như giá, mã trạng thái, số tiền đã định dạng vào file bundle. Bundle giữ thông điệp/nhãn/mẫu câu; giá trị vẫn được tính ở domain rồi trình bày theo `Locale`.
- Khi dùng `MessageFormat`, giữ placeholder và mẫu câu hoàn chỉnh theo từng ngôn ngữ. Kế thừa một câu ở root có thể tạo ngữ pháp không phù hợp cho ngôn ngữ yêu cầu; cần kiểm thử bản dịch.
- Với Java 17, resource bundle properties hỗ trợ UTF-8 theo hành vi chuẩn từ Java 9; hãy lưu tệp đúng encoding, kiểm tra việc đóng gói resource vào classpath/JAR.

## 8. Kiểm tra chính xác nguồn giá trị của key

Có sự khác nhau giữa việc biết **key có thể được tra được** và biết **bundle trực tiếp nào đang sở hữu key**:

- `bundle.containsKey(key)`: có thể trả `true` nhờ **cha**, không chỉ nhờ bundle con.
- `bundle.keySet()`: là **hợp** khóa từ bundle hiện tại và các parent bundle, không có thông tin bundle xuất xứ của từng key.
- `bundle.getLocale()`: báo locale của bundle được chọn, **không báo** locale của từng giá trị lấy qua parent.
- `bundle.getString(key)`: trả nội dung cuối cùng theo ưu tiên con → cha; không cung cấp metadata nguồn.

Nếu nhóm cần báo cáo tỷ lệ dịch trực tiếp ở từng locale, hãy kiểm tra từng file nguồn hoặc bundle nội bộ bằng công cụ QA phù hợp và phân biệt key hiện diện trực tiếp với key kế thừa. Khi dùng class-based bundle, `handleKeySet()` là API `protected` cho khóa riêng của bundle, không thể gọi từ mã ứng dụng bất kỳ như một phương thức public.

**Không nên tự viết thuật toán kiểm tra `containsKey` rồi cố đoán “bản dịch đã có ở locale cụ thể”**: `containsKey` đã tính parent, nên kiểm thử như vậy có thể bỏ lọt các khóa chưa dịch. Bản dịch thiếu đôi khi cần được đánh dấu trong quy trình dịch thay vì để runtime âm thầm xử lý.

## 9. Cache và thay đổi tài nguyên tại runtime

`ResourceBundle.getBundle` mặc định **có cache**. Khi một bundle đã được tải, các lần gọi sau có thể trả đối tượng đã cache, bao gồm quan hệ parent đã được thiết lập. Vì vậy:

- Sửa tệp properties trên đĩa sau khi ứng dụng đang chạy **không đảm bảo** mọi lần `getBundle` lập tức nhìn thấy nội dung mới.
- Thông thường, sửa bản dịch được phân phối thông qua build/deploy lại ứng dụng.
- Nếu cần tải lại có kiểm soát, có thể cân nhắc chính sách TTL/reload với `ResourceBundle.Control` hoặc `ResourceBundle.clearCache(...)` tùy kiến trúc, nhưng việc xóa cache không bảo đảm một đối tượng `ResourceBundle` đã được giữ ở nơi khác tự cập nhật.
- Dữ liệu ở bundle con, cha và root cần được cập nhật đồng bộ; một lần reload có thể phơi bày cấu hình chưa nhất quán nếu triển khai nhiều phiên bản không khớp.
- Với named module và resource provider, cần tuân thủ API module tương ứng; không giả định mọi overload có `Control` đều dùng được.

Thay đổi `Locale.setDefault` cũng không phải cách “làm mới parent chain”: nó làm thay đổi lựa chọn locale mặc định toàn JVM, có thể ảnh hưởng người dùng khác và không giải quyết được cache hoặc dữ liệu thiếu.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nhân bản tất cả key của cha sang bundle con | Bản dịch trùng lặp, khó cập nhật | Chỉ ghi override cần thiết ở bundle chuyên biệt |
| Đặt `key=` ở con với ý định fallback | Giá trị rỗng che mất giá trị cha | Bỏ key ở con nếu muốn kế thừa |
| Nghĩ `containsKey` chứng minh key có trong file `vi_VN` | Đếm sai độ phủ bản dịch | QA từng file trực tiếp, phân biệt inherited keys |
| Nghĩ `getLocale()` chỉ ra file chứa từng key | Sai khi key được lấy từ parent | Theo dõi nguồn riêng trong công cụ QA nếu cần |
| Dùng `messages_vi-VN.properties` | Không theo quy ước tên bundle chuẩn | Dùng `messages_vi_VN.properties` |
| Chỉ tạo file root rồi gọi mọi locale và nghĩ đã dịch đủ | UI trộn hoặc chỉ hiện fallback | Kiểm tra chính sách locale hỗ trợ và chất lượng từng bản |
| Cho rằng fallback chỉ xảy ra khi cả file thiếu | Bỏ qua cơ chế kế thừa từng key | Hiểu cả bước chọn bundle và tra khóa |
| Cho rằng bundle con `extends` bundle cha ở Java source | Nhầm quan hệ ngôn ngữ với runtime parent chain | Để `ResourceBundle.getBundle` xây chain |
| Sửa file runtime rồi chờ tự cập nhật | Cache vẫn giữ dữ liệu cũ | Chính sách reload/deploy rõ ràng |
| Tự nối chuỗi thông báo từ nhiều khóa nhỏ | Sai ngữ pháp giữa ngôn ngữ | Dùng template hoàn chỉnh theo locale |

## 11. Bài tập tự kiểm tra

Bắt đầu từ ba tệp của ví dụ chính, thử các thay đổi sau (mỗi thay đổi là một thí nghiệm riêng, không gộp tất cả cùng lúc):

1. **Xóa `button.save` trong `messages_vi_VN.properties`:** dự đoán kết quả sẽ trở về `Lưu` từ `messages_vi.properties`. Chạy lại và so sánh.
2. **Xóa tiếp `button.save` khỏi `messages_vi.properties`:** dự đoán giá trị sẽ là `Save` từ root.
3. **Đặt `button.cancel=` trong `messages_vi_VN.properties`:** dự đoán `bundle.getString("button.cancel")` trả chuỗi rỗng; không còn kế thừa `Cancel`.
4. **Xóa `messages_vi_VN.properties` khỏi classpath:** `getBundle` chọn `messages_vi` nếu file đó tồn tại. Kiểm tra `getLocale().toLanguageTag()`.
5. **Xóa mọi phiên bản ngôn ngữ của một key:** dự đoán `MissingResourceException` khi gọi `getString`.
6. **Thêm `messages_en.properties` rồi yêu cầu một locale không có bundle riêng:** quan sát ảnh hưởng của default JVM locale trong bước chọn bundle; cần phân biệt với fallback key qua parent.
7. **Sắp xếp `keySet()`:** so sánh số khóa hiệu dụng với số khóa có trong từng file; chúng không nhất thiết bằng nhau do ghi đè và kế thừa.

Mỗi bài tập cho thấy một khía cạnh của cùng một mô hình: **bundle con ghi đè, bundle cha cung cấp phần còn thiếu, còn thuật toán chọn bundle xác định cây cha–con được sử dụng**.

## 12. Điều cần ghi nhớ

Quan hệ giữa bundle con và bundle cha trong Java localization là **cơ chế tra cứu tài nguyên có thứ tự ưu tiên**. Với `messages_vi_VN`, `messages_vi`, `messages` có đủ trên classpath, lời gọi `getString` tìm khóa từ cụ thể đến tổng quát: con → cha ngôn ngữ → root. Cấp đầu tiên có khóa sẽ cung cấp giá trị; nếu cả chuỗi đều không có, chương trình nhận `MissingResourceException`.

Hãy tách bạch ba khái niệm khi thiết kế và gỡ lỗi: **ứng viên bundle được chọn**, **chuỗi parent được tạo**, và **key được tìm thấy ở cấp nào**. Tổ chức bundle theo mức độ chuyên biệt giúp tránh lặp bản dịch, nhưng vẫn cần QA nghiêm ngặt để không che mất các bản dịch còn thiếu.

**Tài liệu tham khảo:**

- Java SE 17, `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17, `ResourceBundle.Control`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html
- Java SE 17, `PropertyResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html
