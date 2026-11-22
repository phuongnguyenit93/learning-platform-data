# Vì sao không đổi locale mặc định theo từng người dùng?

## 1. Vấn đề: một JVM phục vụ nhiều người dùng

Giả sử ứng dụng Java phục vụ đồng thời:

- Người dùng A chọn tiếng Việt, locale `vi-VN`.
- Người dùng B chọn tiếng Anh (Hoa Kỳ), locale `en-US`.
- Người dùng C chọn tiếng Pháp, locale `fr-FR`.

Một cách làm dễ nghĩ tới nhưng sai là mỗi khi nhận yêu cầu của A, B hoặc C, server gọi `Locale.setDefault(requestLocale)` rồi tiếp tục xử lý với các API dùng `Locale.getDefault()`. **Default locale là trạng thái mặc định dùng chung trong JVM, không phải thuộc tính riêng của mỗi request, thread hay người dùng.** Khi B thay đổi nó, các thao tác của A đọc mặc định *sau đó* cũng có thể thấy locale của B.

Quy tắc cần nhớ: **locale của người dùng/request phải được xác định rồi truyền tường minh qua luồng xử lý**, còn JVM default locale chỉ nên đóng vai trò mặc định cấp tiến trình (chẳng hạn một ứng dụng đơn ngôn ngữ hoặc lựa chọn ban đầu khi chưa có preference).

Sau bài này, bạn có thể giải thích phạm vi `getDefault/setDefault`, nhận diện lỗi race condition trong ứng dụng nhiều request, xử lý đúng các category `DISPLAY`/`FORMAT`, thiết kế phương thức nhận `Locale` rõ ràng và kiểm thử mà không để rò trạng thái toàn cục.

## 2. `Locale.getDefault()` và `Locale.setDefault()` tác động ở phạm vi nào?

`java.util.Locale` có các API:

| API | Ý nghĩa |
| --- | --- |
| `Locale.getDefault()` | Trả locale mặc định chung (base default locale) của JVM |
| `Locale.setDefault(Locale)` | Thay mặc định chung; đồng thời thiết lập default cho các category `DISPLAY` và `FORMAT` |
| `Locale.getDefault(Locale.Category.FORMAT)` | Trả mặc định category dùng cho định dạng (số, ngày/giờ, tiền tệ trong API hỗ trợ category) |
| `Locale.getDefault(Locale.Category.DISPLAY)` | Trả mặc định category cho cách hiển thị tên ngôn ngữ/vùng |
| `Locale.setDefault(Locale.Category, Locale)` | Thay category default tương ứng ở phạm vi JVM, **không** tạo locale riêng cho thread |

Các giá trị mặc định ban đầu thường được thiết lập dựa trên cấu hình hệ điều hành và các thuộc tính môi trường/khởi động Java; chúng có thể được thay đổi khi chương trình chạy. Vì vậy, `Locale.getDefault()` không phải một hằng số bất biến suốt vòng đời JVM.

Điều **không đúng** khi gọi `setDefault`:

- Không gắn locale vào `Thread.currentThread()` hay request hiện tại.
- Không bảo đảm những formatter/resource đã tạo từ trước tự đổi theo default mới; một số API lấy mặc định vào lúc tạo đối tượng và có thể cache dữ liệu.
- Không chỉ tác động đến người dùng đang đăng nhập.
- Không trở nên an toàn chỉ vì một servlet request được xử lý trên một thread riêng.
- Không làm thay đổi múi giờ mặc định: `Locale` và `TimeZone`/`ZoneId` là các khái niệm tách biệt.

Một hệ thống có thể chạy nhiều JVM/process, mỗi process có default riêng. Bên trong **cùng một JVM**, mọi luồng dùng chung state này, dù các request được xử lý bởi thread pool khác nhau.

## 3. Race condition: chuyện gì xảy ra khi hai request chạy đồng thời?

Xét trình tự:

1. Request A (người dùng Việt Nam) gọi `Locale.setDefault(vi-VN)`.
2. A tạm dừng trước bước định dạng dữ liệu.
3. Request B gọi `Locale.setDefault(en-US)`.
4. A tiếp tục, gọi `Locale.getDefault()` hoặc tạo formatter dùng default. A có thể nhận `en-US`, trái với sở thích `vi-VN`.
5. Nếu A lại set default, các thao tác khác của B hoặc C cũng có thể bị ảnh hưởng.

`Locale.setDefault` thay đổi trạng thái toàn cục; ngay cả khi từng thao tác đọc/ghi mặc định có cơ chế đồng bộ ở mức API, **chuỗi nhiều bước “set locale → làm việc → khôi phục” không trở thành một giao dịch riêng tư cho request**. Giữ lock cho một đoạn code cũng không kiểm soát được toàn bộ thư viện và luồng khác đang đọc default trong JVM.

### Ví dụ Java 17+ có thứ tự chạy xác định

File `DefaultLocaleRaceDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class DefaultLocaleRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        Locale previous = Locale.getDefault();
        CountDownLatch aliceHasSet = new CountDownLatch(1);
        CountDownLatch bobHasSet = new CountDownLatch(1);
        AtomicReference<String> aliceObserved = new AtomicReference<>();
        AtomicReference<String> bobObserved = new AtomicReference<>();

        Thread alice = new Thread(() -> {
            Locale.setDefault(Locale.forLanguageTag("vi-VN"));
            aliceHasSet.countDown();
            try {
                bobHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            aliceObserved.set(Locale.getDefault().toLanguageTag());
        });

        Thread bob = new Thread(() -> {
            try {
                aliceHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            Locale.setDefault(Locale.US);
            bobObserved.set(Locale.getDefault().toLanguageTag());
            bobHasSet.countDown();
        });

        try {
            alice.start();
            bob.start();
            alice.join();
            bob.join();

            System.out.println("Alice expects: vi-VN");
            System.out.println("Alice sees: " + aliceObserved.get());
            System.out.println("Bob expects: en-US");
            System.out.println("Bob sees: " + bobObserved.get());
        } finally {
            // Chỉ để thí nghiệm không để lại thay đổi mặc định.
            Locale.setDefault(previous);
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac DefaultLocaleRaceDemo.java
java DefaultLocaleRaceDemo
```

Kết quả:

```text
Alice expects: vi-VN
Alice sees: en-US
Bob expects: en-US
Bob sees: en-US
```

Hai `CountDownLatch` buộc Bob thay default **sau khi** Alice đặt `vi-VN` và **trước khi** Alice đọc. `AtomicReference` chỉ lưu kết quả từng thread để main in theo thứ tự ổn định. Ví dụ cố tình sử dụng `setDefault` để phơi bày lỗi; **không** phải mẫu code khuyên dùng trong server. Phần `finally` chỉ khôi phục môi trường cho thí nghiệm đã đợi hai thread kết thúc; thêm `finally` vào request handler sản xuất **không giải quyết race** giữa các request.

## 4. Các lỗi thực tế do đổi default theo request

| Tình huống | Sai lệch có thể xảy ra |
| --- | --- |
| `NumberFormat.getNumberInstance()` không truyền locale | Dấu phân cách thập phân/nhóm số dựa trên locale mặc định tại thời điểm lấy formatter |
| `DateFormat.getDateInstance()` không truyền locale | Tên tháng, cách viết ngày có thể đổi theo default |
| `DateTimeFormatter` dùng mẫu có tên tháng nhưng không cấu hình locale phù hợp | Chuỗi tên tháng/ngày có thể không theo ngôn ngữ của người dùng |
| `ResourceBundle.getBundle(baseName)` không truyền locale | Có thể chọn bundle từ default khác với ngôn ngữ request |
| Thư viện nội bộ gọi `Locale.getDefault()` | Request đang xử lý có thể dùng preference của request khác |
| Log/audit ghi dữ liệu định dạng theo default biến đổi | Khó tái hiện hoặc so sánh dữ liệu giữa những lần chạy |
| Chạy test thay default mà không phục hồi | Test phía sau phụ thuộc thứ tự chạy và thất bại ngẫu nhiên |

**Không phải mọi API locale-sensitive đều đọc default ở cùng thời điểm.** Một formatter có thể giữ locale khi được tạo; formatter khác có thể có default tại lần gọi API. Vì thế cách sửa đúng phải dựa trên việc truyền dữ liệu cấu hình rõ ràng, không trông chờ lúc nào runtime đọc default.

Ngoài ra, xử lý sai locale còn làm ảnh hưởng chức năng: parse `"1,234"` có thể được hiểu khác giữa các convention; hiển thị ngày dạng `01/02/2026` gây nhầm ngày/tháng; so khớp/chuyển chữ hoa thường cần quy tắc ngôn ngữ rõ ràng. Những vấn đề này cần API và chính sách đúng, không phải liên tục đổi JVM default.

## 5. Cách đúng: truyền `Locale` của người dùng tường minh

Mẫu quan trọng là **resolve locale một lần cho request → truyền locale tới các hàm định dạng, bản dịch và phản hồi**:

```text
HTTP request / user profile / accepted language preference
                       |
                       v
           Xác thực + chọn Locale được hỗ trợ
                       |
                       v
             Request context / tham số hàm
                       |
             +---------+---------+
             |         |         |
             v         v         v
        NumberFormat  DateTime   ResourceBundle
                      Formatter
             \         |         /
              \        |        /
               v       v       v
               Trả kết quả đúng người dùng
```

Các nguồn preference có thể gồm cấu hình tài khoản, query parameter được cho phép, cookie phiên hoặc header HTTP `Accept-Language`. Nếu người dùng chỉ gửi một chuỗi dạng `vi-VN`, ứng dụng vẫn cần kiểm tra cú pháp, giới hạn tập locale được hỗ trợ và áp dụng fallback theo chính sách. Toàn bộ header `Accept-Language` gồm các tag/trọng số (`q`) **không phải một language tag đơn**.

### Ví dụ Java 17+: định dạng theo từng request mà không gọi `setDefault`

File `ExplicitLocaleDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class ExplicitLocaleDemo {
    static String renderNumber(double value, Locale requestLocale) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(requestLocale);
        formatter.setGroupingUsed(false); // Giữ output đơn giản.
        return requestLocale.toLanguageTag()
                + ": " + formatter.format(value);
    }

    public static void main(String[] args) {
        Locale alice = Locale.forLanguageTag("vi-VN");
        Locale bob = Locale.forLanguageTag("en-US");

        System.out.println(renderNumber(1234.5, alice));
        System.out.println(renderNumber(1234.5, bob));
    }
}
```

```bash
javac ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

Đầu ra với dữ liệu locale tiêu chuẩn của JDK:

```text
vi-VN: 1234,5
en-US: 1234.5
```

Điểm cốt lõi là cả hai phép định dạng nhận **đối tượng `Locale` riêng** và không thay đổi JVM default. Việc dùng `setGroupingUsed(false)` chỉ tắt phân nhóm hàng nghìn để ví dụ tập trung vào dấu thập phân. Hình thức hiển thị có thể chịu ảnh hưởng provider/dữ liệu locale của môi trường Java; dùng API để định dạng theo locale, không tự tạo dấu bằng cách thay ký tự trong chuỗi.

### Các API thường có overload nhận locale

```java
// Các đoạn minh họa trong một phương thức đã có biến requestLocale.
NumberFormat numberFormatter =
        NumberFormat.getNumberInstance(requestLocale);

NumberFormat currencyFormatter =
        NumberFormat.getCurrencyInstance(requestLocale);

java.text.DateFormat dateFormatter =
        java.text.DateFormat.getDateInstance(
                java.text.DateFormat.MEDIUM, requestLocale);

java.time.format.DateTimeFormatter dateTimeFormatter =
        java.time.format.DateTimeFormatter
                .ofLocalizedDate(java.time.format.FormatStyle.MEDIUM)
                .withLocale(requestLocale);

java.util.ResourceBundle bundle =
        java.util.ResourceBundle.getBundle("messages", requestLocale);
```

Đây là **đoạn mã minh họa**, không phải một file Java tự biên dịch: `requestLocale` phải được khai báo và có sẵn trong phạm vi, còn `messages` phải có các resource bundle tương ứng trên classpath.

Với `ResourceBundle`, truyền locale giúp chọn candidate bundle theo yêu cầu; nếu không có tài nguyên tương ứng, cơ chế fallback mặc định vẫn có thể xét default locale. Nếu cần fallback bất biến, được kiểm soát chặt hoặc tách biệt hoàn toàn với JVM default, thiết kế chính sách lookup bundle rõ ràng (ví dụ `ResourceBundle.Control` trong môi trường hỗ trợ hoặc quản lý fallback của ứng dụng) và cung cấp tập bundle hợp lệ. Truyền `Locale` là bước cần thiết nhưng không tự bảo đảm mọi chuỗi đã dịch đều tồn tại.

## 6. `Locale.Category.FORMAT` và `DISPLAY` có giải quyết vấn đề không?

Java cho phép hai nhóm mặc định chuyên biệt:

- `Locale.Category.FORMAT`: dành cho hoạt động định dạng phụ thuộc locale.
- `Locale.Category.DISPLAY`: dành cho tên hiển thị language, country và các đối tượng liên quan.

Ví dụ:

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
```

Lệnh này **vẫn thay default dùng chung của category FORMAT trong JVM**. Nó không tạo "FORMAT locale của người dùng A". Một request khác có thể ghi đè category này; các formatter mới chọn category default có thể bị ảnh hưởng. `Locale.setDefault(Locale)` cũng thay cả các category default.

### Minh họa Java 17+ về phạm vi category

File `LocaleCategoryDemo.java`:

```java
import java.util.Locale;

public class LocaleCategoryDemo {
    public static void main(String[] args) {
        Locale beforeBase = Locale.getDefault();
        Locale beforeFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale beforeDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.FRANCE);

            System.out.println(Locale.getDefault().toLanguageTag());
            System.out.println(
                    Locale.getDefault(Locale.Category.FORMAT)
                            .toLanguageTag());
            System.out.println(
                    Locale.getDefault(Locale.Category.DISPLAY)
                            .toLanguageTag());
        } finally {
            Locale.setDefault(beforeBase);
            Locale.setDefault(
                    Locale.Category.FORMAT, beforeFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, beforeDisplay);
        }
    }
}
```

```bash
javac LocaleCategoryDemo.java
java LocaleCategoryDemo
```

Kết quả:

```text
en-US
fr-FR
en-US
```

Nghĩa là lúc này base default là `en-US`, format default là `fr-FR` và display default là `en-US`. Việc thiết lập các giá trị khác nhau **không** tạo cách ly theo người dùng. Chỉ thay đổi category trong khởi tạo tiến trình hoặc trong test được kiểm soát; đừng gọi theo mỗi request.

## 7. Không đồng nhất locale với thread context hoặc múi giờ

`Locale` mặc định **khác** với những context khác trong ứng dụng:

- `ThreadLocal<Locale>` chỉ gắn giá trị vào một thread nhất định, nhưng **không thay đổi `Locale.getDefault()`** và các API không tự chuyển sang đọc `ThreadLocal` đó.
- Server dùng thread pool có thể tái sử dụng cùng thread cho nhiều request; nếu dùng `ThreadLocal` làm request context, phải quản lý vòng đời và `remove()` trong `finally` hoặc dùng cơ chế context của framework. Với xử lý bất đồng bộ/chuyển thread, context cũng không tự động được mang theo.
- Một framework web có thể có cơ chế `LocaleResolver` hay context riêng; đó là tầng quản lý locale của framework, không phải gọi `Locale.setDefault` cho JVM.
- `ZoneId`/`TimeZone` biểu diễn múi giờ. Người dùng cùng locale `en-US` vẫn có thể sống ở các múi giờ khác nhau; một người dùng `vi-VN` cũng có thể sống ở nước ngoài. Không suy ra múi giờ từ locale và không dùng `TimeZone.setDefault` theo request.

Trong code Java thông thường, cách dễ hiểu và kiểm thử nhất là truyền `Locale` trực tiếp qua tham số hoặc giữ nó trong đối tượng context **bất biến theo request**, rồi đưa nó vào các API hỗ trợ locale. Chỉ dùng `ThreadLocal` khi đã có một cơ chế quản lý scope rõ ràng và được mọi thành phần liên quan đọc đúng cách.

## 8. Quy tắc chọn locale cho request

Một quy trình thường dùng:

1. **Đọc preference** từ hồ sơ người dùng hoặc request. Nếu nguồn không tin cậy, không giả định chuỗi đã hợp lệ.
2. **Phân tích cú pháp**: với một BCP 47 tag riêng lẻ, dùng `Locale.Builder.setLanguageTag(...)` để phát hiện malformed input; với toàn bộ `Accept-Language`, cần parser cho danh sách language ranges, ví dụ `Locale.LanguageRange.parse(...)`, và xử lý quy tắc ưu tiên/trọng số.
3. **Đối chiếu danh sách hỗ trợ** của ứng dụng: locale hợp cú pháp chưa chắc có tài nguyên bản dịch.
4. **Fallback có chủ đích**: ví dụ `vi-VN` nếu chưa có preference hoặc locale được yêu cầu không hỗ trợ. Có thể ưu tiên matching language rồi mới fallback, tùy nghiệp vụ.
5. **Truyền explicit `Locale`** vào service, formatter, resource lookup và response rendering. Không gọi `setDefault` khi xử lý yêu cầu.
6. **Gắn nhãn/quan sát có kiểm soát**: khi debug, log `requestLocale.toLanguageTag()` thay vì suy ra người dùng dựa trên `Locale.getDefault()`.

Để tránh nhầm lẫn, **locale của response** và **ngôn ngữ dịch nội dung** có thể cần chính sách đồng bộ. Ví dụ nếu request chọn `fr-CA` nhưng ứng dụng chỉ có bản dịch `fr` và formatter hỗ trợ `fr-CA`, có thể dùng `fr-CA` cho số/ngày và `fr` cho text resource; quy tắc đó phải được thiết kế tường minh.

## 9. Kiểm thử: khi nào có thể dùng `setDefault`?

Có những bài test cần chứng minh code không phụ thuộc mặc định của máy chạy CI. Trong **test đơn luồng được cô lập**, bạn có thể lưu default ban đầu, tạm đổi, chạy kiểm tra, rồi khôi phục trong `finally`. Nếu test chạy song song cùng một JVM, thay default vẫn ảnh hưởng test khác; cách cô lập tốt nhất là **truyền `Locale` trực tiếp** hoặc chạy thí nghiệm về global default trong JVM riêng.

Ví dụ hướng kiểm thử đúng:

- Kiểm tra `renderNumber(value, Locale.FRANCE)` cho ra dạng địa phương hóa đúng, bất kể JVM có default nào.
- Khởi tạo đối tượng render/service với locale tường minh, gọi nhiều lần đồng thời với các locale khác nhau; kết quả phải độc lập với thứ tự request.
- Với test buộc sửa global default, vô hiệu chạy song song của phần test liên quan, bao gồm code thư viện dùng default và khôi phục đủ base/`FORMAT`/`DISPLAY`. Không mặc định mỗi test có `finally` là đã an toàn khi test runner song song.

Đừng đưa `Locale.setDefault` vào constructor singleton, request filter hay interceptor như giải pháp ngôn ngữ theo người dùng. Một singleton giữ `Locale` riêng theo request cũng nguy hiểm nếu trường mutable bị request khác ghi đè; ưu tiên truyền tham số hoặc đối tượng scope độc lập.

## 10. Lỗi thường gặp và cách sửa

| Cách làm sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `Locale.setDefault(userLocale)` trong request handler | Thay giá trị toàn cục, gây xung đột request | `NumberFormat.get...Instance(userLocale)` và các overload nhận `Locale` |
| `setDefault` ở đầu request, khôi phục ở cuối | Hai request có thể xen giữa phần xử lý | Không sửa default cho từng request |
| Nghĩ `Locale.setDefault(Category.FORMAT, ...)` là per-thread | Category cũng là trạng thái dùng chung | Truyền locale tường minh vào formatter |
| Đọc default một lần rồi lưu vào static singleton làm preference của user | Đóng băng preference không đúng người dùng | Resolve preference từ context của mỗi request |
| Dùng `ThreadLocal` mà không `remove` | Thread pool có thể giữ nhầm state của request trước | Quản lý scope và cleanup; ưu tiên tham số hàm |
| Dùng `Locale.getDefault()` để suy ra ngôn ngữ của request | Phản ánh cấu hình JVM, không phải user | Dùng locale đã resolve từ nguồn yêu cầu |
| Coi `Locale` là múi giờ | Hiển thị giờ sai | Truyền `ZoneId` độc lập |
| Test thay default chạy song song | Test có thể flaky do trạng thái chung | Test explicit locale hoặc cô lập JVM |

## 11. Tự kiểm tra

1. Một JVM có 100 request đồng thời. Gọi `Locale.setDefault(Locale.US)` trong request A có tạo locale riêng cho A không? **Không**, default được chia sẻ trong JVM.
2. `Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE)` có chỉ ảnh hưởng thread hiện tại không? **Không**; category display default vẫn ở cấp JVM.
3. Vì sao `try/finally` khôi phục default ở cuối mỗi request vẫn không đủ? **Vì request khác có thể đọc/ghi default giữa lúc request hiện tại đã set và chưa kịp khôi phục**.
4. Cách truyền locale vào định dạng số? **`NumberFormat.getNumberInstance(requestLocale)`**.
5. `ThreadLocal<Locale>` có khiến `Locale.getDefault()` tự đổi theo thread không? **Không**. Code phải chủ động đọc context và truyền vào API.
6. Nếu có `vi-VN` nhưng người dùng ở múi giờ khác Việt Nam, có suy ra múi giờ từ locale không? **Không**; dùng `ZoneId` từ cấu hình thích hợp.

## Tài liệu tham khảo

- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `getDefault`, `setDefault`, `Category`, `forLanguageTag` và các API liên quan.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): các factory nhận locale.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale` và các formatter localized.
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): locale lookup và fallback.
