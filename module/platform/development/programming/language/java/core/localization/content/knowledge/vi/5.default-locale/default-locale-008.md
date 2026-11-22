# Khôi phục locale mặc định khi kiểm thử thay đổi cấu hình chung trong Java

## 1. Bối cảnh: vì sao một bài kiểm thử có thể làm hỏng bài khác?

`Locale.getDefault()` trả về locale mặc định của JVM khi code không được truyền một `Locale` cụ thể. Một số API và thư viện dựa vào mặc định đó để lựa chọn ngôn ngữ, quy tắc hiển thị hoặc định dạng. Trong kiểm thử, lập trình viên đôi khi gọi `Locale.setDefault(...)` để mô phỏng môi trường người dùng:

```java
Locale.setDefault(Locale.FRANCE);
// Gọi code dùng Locale.getDefault()...
```

Đoạn minh họa trên thay đổi **trạng thái chung của cả JVM**, không chỉ của phương thức test hiện tại. Nếu kiểm thử kết thúc mà chưa đặt lại giá trị ban đầu, những test chạy sau có thể đọc locale khác so với lúc bắt đầu, tạo lỗi phụ thuộc thứ tự chạy, kết quả định dạng khác nhau, hoặc hành vi khó tái hiện trên CI.

Một lỗi khác: người viết test nhớ khôi phục `Locale.getDefault()` nhưng quên các mặc định chuyên biệt `Locale.Category.DISPLAY` và `Locale.Category.FORMAT`. Cách khôi phục đúng phải dựa trên **những giá trị thực tế đã có trước test**.

**Mục tiêu bài học:** chụp (snapshot) các mặc định locale liên quan, thử thay đổi chúng, dùng `try/finally` để khôi phục ngay cả khi test thất bại, kiểm tra trạng thái sau phục hồi và hiểu vì sao kiểm thử song song vẫn cần quản lý riêng.

## 2. Hiểu ba trạng thái locale mặc định

Java hỗ trợ locale mặc định chung và hai category mặc định:

| Giá trị cần đọc | API | Vai trò |
| --- | --- | --- |
| Mặc định chung | `Locale.getDefault()` | Locale mặc định của JVM, thường dùng khi một API không chỉ định category. |
| Mặc định hiển thị | `Locale.getDefault(Locale.Category.DISPLAY)` | Ưu tiên cho tên hoặc văn bản phục vụ hiển thị, ví dụ tên ngôn ngữ/địa danh qua các API có category. |
| Mặc định định dạng | `Locale.getDefault(Locale.Category.FORMAT)` | Ưu tiên cho định dạng số, tiền tệ, ngày giờ ở các API dùng category `FORMAT`. |

Các setter tương ứng:

```java
Locale.setDefault(Locale.US);
Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
```

Đây là các câu lệnh minh họa, chưa phải chương trình độc lập.

Cần nắm hai quy tắc:

1. `Locale.setDefault(Locale)` thay đổi locale mặc định chung **và đặt lại mặc định của cả hai category `DISPLAY`, `FORMAT`** về locale mới.
2. `Locale.setDefault(Locale.Category, Locale)` chỉ thay đổi mặc định của category được chỉ định; nó không tự đồng bộ mọi category và base locale.

Do đó, ba giá trị có thể khác nhau hoàn toàn. Chẳng hạn, sau ba lệnh trên, base là `en-US`, DISPLAY là `fr-FR`, FORMAT là `de-DE`.

Dù có thể thiết lập từng category riêng, các giá trị vẫn là **trạng thái dùng chung trong JVM**, không trở thành cấu hình dành riêng cho thread hay test case.

## 3. Quy tắc khôi phục an toàn: snapshot → try/finally → restore

Mẫu tối thiểu:

```java
Locale originalBase = Locale.getDefault();
Locale originalDisplay = Locale.getDefault(Locale.Category.DISPLAY);
Locale originalFormat = Locale.getDefault(Locale.Category.FORMAT);

try {
    Locale.setDefault(Locale.US);
    Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
    Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

    // Thực hiện các assertion của bài kiểm thử.
} finally {
    Locale.setDefault(originalBase);
    Locale.setDefault(Locale.Category.DISPLAY, originalDisplay);
    Locale.setDefault(Locale.Category.FORMAT, originalFormat);
}
```

Đoạn này đặt bên trong phương thức Java. Thứ tự phục hồi **rất quan trọng**: phục hồi base trước, vì `setDefault(Locale)` sẽ đặt lại hai category; sau đó khôi phục `DISPLAY` và `FORMAT` từ snapshot để bảo toàn mọi giá trị khác nhau ban đầu.

`finally` chạy khi khối `try` kết thúc bình thường hoặc khi có exception/assertion failure (trừ các trường hợp tiến trình JVM bị dừng đột ngột, chẳng hạn `System.exit`, crash hoặc máy bị tắt). Nếu một assertion thất bại, ngoại lệ vẫn được ném tiếp sau khi `finally` chạy; không nên nuốt lỗi kiểm thử chỉ để ghi log.

**Không hard-code việc khôi phục về `Locale.US`, `Locale.ENGLISH` hoặc `Locale.getDefault()` được gọi ở cuối.** “Mặc định ban đầu” khác nhau giữa máy cá nhân, CI, container và cấu hình chạy test. Giá trị mặc định phải được chụp **trước bất kỳ lệnh đổi locale nào**.

### Vì sao không chỉ lưu base?

Giả sử trước test có:

```text
base    = en-US
DISPLAY = fr-FR
FORMAT  = de-DE
```

Nếu test gọi `Locale.setDefault(Locale.JAPAN)`, cả ba giá trị có thể trở thành `ja-JP`. Sau đó chỉ gọi `Locale.setDefault(originalBase)` sẽ cho:

```text
base    = en-US
DISPLAY = en-US
FORMAT  = en-US
```

Đây **chưa phải trạng thái ban đầu**, vì hai category đã mất override `fr-FR` và `de-DE`. Snapshot đầy đủ ba giá trị mới có thể khôi phục chính xác.

## 4. Chương trình Java 17+ chạy độc lập

Tạo tệp **`LocaleDefaultRestoreDemo.java`**. Ví dụ dùng một `record` để gom ba giá trị snapshot. Chương trình hiển thị các giá trị được thay đổi trong test, phục hồi ở `finally` và kiểm tra rằng toàn bộ ba trạng thái khớp snapshot. Kết quả không phụ thuộc locale ban đầu của máy.

```java
import java.util.Locale;

public class LocaleDefaultRestoreDemo {

    private record SavedDefaults(
            Locale base,
            Locale display,
            Locale format) {

        static SavedDefaults capture() {
            return new SavedDefaults(
                    Locale.getDefault(),
                    Locale.getDefault(Locale.Category.DISPLAY),
                    Locale.getDefault(Locale.Category.FORMAT)
            );
        }

        void restore() {
            // Đặt base trước vì thao tác này cũng reset hai category.
            Locale.setDefault(base);
            Locale.setDefault(Locale.Category.DISPLAY, display);
            Locale.setDefault(Locale.Category.FORMAT, format);
        }

        boolean matchesCurrent() {
            return base.equals(Locale.getDefault())
                    && display.equals(
                            Locale.getDefault(Locale.Category.DISPLAY))
                    && format.equals(
                            Locale.getDefault(Locale.Category.FORMAT));
        }
    }

    public static void main(String[] args) {
        SavedDefaults saved = SavedDefaults.capture();

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.DISPLAY, Locale.FRANCE);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.GERMANY);

            System.out.println("base="
                    + Locale.getDefault().toLanguageTag());
            System.out.println("display="
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("format="
                    + Locale.getDefault(
                            Locale.Category.FORMAT).toLanguageTag());

            if (!Locale.GERMANY.equals(
                    Locale.getDefault(Locale.Category.FORMAT))) {
                throw new AssertionError("FORMAT was not set");
            }
        } finally {
            saved.restore();
        }

        System.out.println("restored=" + saved.matchesCurrent());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocaleDefaultRestoreDemo.java
java LocaleDefaultRestoreDemo
```

**Stdout chính xác:**

```text
base=en-US
display=fr-FR
format=de-DE
restored=true
```

*Vì sao `restored=true`?* `SavedDefaults.capture()` ghi lại ba `Locale` trước khi code đổi trạng thái. `try` thiết lập môi trường giả lập; `finally` phục hồi base, DISPLAY và FORMAT theo thứ tự an toàn. `matchesCurrent()` so sánh các object `Locale` với ảnh chụp trước test, không đoán trước locale của máy.

Nếu một assertion trong `try` ném `AssertionError`, khối `finally` vẫn được chạy, sau đó lỗi được chuyển ra ngoài như kỳ vọng. Dòng `restored=true` nằm sau `finally` nên trong trường hợp assertion thất bại sẽ không được in; điều đó không đồng nghĩa khôi phục không chạy.

### Vì sao record phù hợp ở đây?

`record` (Java 17) giữ ba trường `Locale` làm dữ liệu snapshot có tên rõ ràng. Bạn cũng có thể dùng một class thông thường, nhưng phải lưu đủ ba thành phần. Các getter `getDefault(...)` trả các đối tượng `Locale`; việc chụp các tham chiếu này là đủ vì bản thân `Locale` bất biến theo API, còn trạng thái có thể thay đổi chính là các biến static mặc định của JVM.

## 5. Áp dụng với JUnit 5

Nếu một test cần thay đổi mặc định chung, hãy bao toàn bộ thao tác bằng `try/finally` ngay trong test. Đoạn minh họa sau dùng JUnit Jupiter 5; muốn chạy cần dự án có dependency JUnit 5 và test runner tương ứng. Đây **không phải một chương trình Java độc lập chỉ cần `javac`**.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock("jvm-default-locale")
class LocaleSensitiveTest {

    @Test
    void restoresDefaultsAfterAssertions() {
        Locale base = Locale.getDefault();
        Locale display =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale format =
                Locale.getDefault(Locale.Category.FORMAT);

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.GERMANY);

            assertEquals(Locale.US, Locale.getDefault());
            assertEquals(
                    Locale.GERMANY,
                    Locale.getDefault(Locale.Category.FORMAT));
        } finally {
            Locale.setDefault(base);
            Locale.setDefault(Locale.Category.DISPLAY, display);
            Locale.setDefault(Locale.Category.FORMAT, format);
        }
    }
}
```

`@ResourceLock("jvm-default-locale")` giúp JUnit Jupiter điều phối những test dùng **cùng tên tài nguyên khóa** khi thực thi song song trong cùng test plan. Mọi test thay đổi/đọc locale mặc định theo cách phụ thuộc trạng thái đều phải hợp tác dùng cùng khóa thích hợp; annotation không thể khóa các thread của ứng dụng hoặc thư viện ngoài cơ chế kiểm thử. Nếu toàn bộ bộ kiểm thử có nhiều thành phần không hợp tác hoặc có thread nền đọc locale, cách đáng tin hơn là **không đổi trạng thái chung** hoặc tách test sang JVM riêng.

### Dùng `@BeforeEach` / `@AfterEach` hay `try/finally`?

`@BeforeEach` có thể lưu snapshot vào field và `@AfterEach` phục hồi, tiện nếu nhiều test cần cùng mẫu. Tuy nhiên, nó đòi hỏi quản lý vòng đời và tránh null khi setup bị lỗi. Với một test duy nhất, `try/finally` dễ kiểm chứng hơn vì snapshot và restore đặt cạnh nhau. Nếu dùng lifecycle hooks, vẫn phải snapshot trước khi bất kỳ setup nào đổi mặc định, và khôi phục cả ba giá trị.

Khi framework hỗ trợ helper hoặc extension để quản lý locale tạm thời, có thể áp dụng để tránh lặp code, nhưng phải kiểm tra nó có hỗ trợ và phục hồi **cả DISPLAY và FORMAT** theo yêu cầu test hay không.

## 6. Những tình huống cần kiểm thử

| Tình huống | Điều cần xác minh |
| --- | --- |
| Test chạy bình thường | Sau test, ba mặc định khớp snapshot; không còn ảnh hưởng thứ tự. |
| Assertion ném `AssertionError` | `finally` vẫn phục hồi; framework vẫn báo test thất bại. |
| Code thử ném `RuntimeException` | Phục hồi xảy ra rồi ngoại lệ được chuyển tiếp; không che giấu lỗi. |
| Base, DISPLAY, FORMAT ban đầu khác nhau | Cả ba được phục hồi, không chỉ base. |
| Test chỉ sửa một category | Category còn lại và base không bị làm sai trong lúc khôi phục. |
| Test lồng nhau, cùng thread | Mỗi mức snapshot tại điểm vào và phục hồi theo thứ tự LIFO. |
| Test chạy song song trên cùng JVM | Cần phối hợp khóa hoặc tách JVM; `try/finally` một mình không bảo vệ khỏi race condition. |
| Test ở CI có locale khác máy cá nhân | Không giả định locale đầu vào cố định; khẳng định dựa trên snapshot. |

### Ví dụ về lỗi thứ tự test

```text
Test A:
  Locale.setDefault(Locale.FRANCE)
  assertion thành công
  quên restore
         ↓
Test B:
  khởi tạo formatter không truyền Locale
  nhận locale fr-FR thay vì môi trường ban đầu
         ↓
B có thể sai dù chạy một mình thì đúng
```

Khi bổ sung `try/finally` vào A, test B không còn nhận ảnh hưởng kéo dài từ A trong chuỗi chạy tuần tự. Nếu A và B thực sự chạy **đồng thời**, B vẫn có thể quan sát locale tạm thời của A; vì vậy phần kiểm soát concurrency phải được giải quyết riêng.

## 7. Kiểm thử song song và giới hạn của `try/finally`

Giả sử hai test cùng chạy trên một JVM:

```text
Thời điểm       Test A                         Test B
t0             lưu base=vi-VN
t1             setDefault(en-US)
t2                                            lưu base=en-US
t3                                            setDefault(fr-FR)
t4             restore(vi-VN)
t5                                            chạy assertion, thấy vi-VN
t6                                            restore(en-US)
Kết thúc       JVM còn en-US, dù ban đầu là vi-VN
```

Cả hai test đều có `try/finally`, nhưng do snapshot và restore bị đan xen, trạng thái cuối vẫn sai. **`try/finally` đảm bảo đường đi phục hồi trong một luồng điều khiển; nó không biến trạng thái JVM thành thread-local và không đảm bảo isolation giữa các test song song.**

Các phương án phù hợp:

1. **Ưu tiên truyền `Locale` trực tiếp vào code dưới test.** Ví dụ dùng `NumberFormat.getNumberInstance(locale)` hoặc `DateTimeFormatter.withLocale(locale)`; khi đó không cần gọi `Locale.setDefault(...)` trong unit test.
2. **Nếu phải test legacy code đọc default locale, chạy tuần tự hoặc khóa cùng một tài nguyên.** Đồng bộ hóa chỉ hữu ích khi mọi code liên quan tuân theo cùng quy tắc khóa. JUnit `@ResourceLock` là cơ chế điều phối test JUnit, không phải khóa ở toàn JVM.
3. **Khi cần cô lập tuyệt đối khỏi các test khác, chạy test trong process/JVM riêng.** Mỗi JVM có default locale riêng; không chia sẻ static state.

Một `synchronized` trên object trong một class test chỉ bảo vệ các thread cũng dùng đúng object đó. Nó không ngăn code ngoài lock gọi `Locale.setDefault(...)`, nên không thể xem là biện pháp chung cho mọi test.

## 8. Cách kiểm tra một lần thay đổi locale có tác dụng như mong muốn

Các API khác nhau dùng mặc định theo những cách khác nhau:

- `Locale.getDefault()` trả base; `Locale.getDefault(Locale.Category.DISPLAY)` trả default DISPLAY; `Locale.getDefault(Locale.Category.FORMAT)` trả default FORMAT.
- Một số formatter không được truyền locale sẽ tra mặc định theo category tương ứng **khi được tạo**. Formatter đã khởi tạo từ trước có thể tiếp tục giữ cấu hình cũ; không nên giả định đổi default làm tất cả object đã có tự cập nhật.
- Những API nhận tham số `Locale` tường minh thường sử dụng tham số đó thay vì default; kiểm thử chúng không cần sửa default JVM.

Khi viết assertion, nên kiểm tra trạng thái qua getter tương ứng thay vì tin rằng thay đổi một getter sẽ ảnh hưởng ngay tất cả thư viện. Nếu kiểm thử định dạng chuỗi, các dữ liệu locale của JDK/CLDR có thể thay đổi đôi chút theo phiên bản; phân biệt rõ yêu cầu hợp đồng của ứng dụng với biểu diễn phụ thuộc dữ liệu JDK.

Đặc biệt, `Locale.setDefault(...)` **không phải** thao tác đổi `TimeZone.setDefault(...)`. Nếu test thay đổi cả locale và time zone, cần snapshot/restore độc lập từng loại trạng thái; đừng nhầm `Locale.Category.FORMAT` với múi giờ.

## 9. Các lỗi dễ mắc khi khôi phục locale

| Lỗi | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| Khôi phục về `Locale.US` mặc định | Trạng thái ban đầu của CI có thể khác `US`. | Chụp `Locale.getDefault()` trước test. |
| Lưu base nhưng bỏ qua DISPLAY/FORMAT | Mất override category đã có từ trước. | Lưu và phục hồi cả ba. |
| Restore category trước rồi gọi `setDefault(base)` cuối | Lệnh cuối reset các category vừa phục hồi. | Restore **base trước, category sau**. |
| Đặt restore sau assertion mà không dùng `finally` | Assertion failure khiến restore bị bỏ qua. | Bao thao tác thay đổi trong `try/finally`. |
| Chụp snapshot sau khi gọi `setDefault(...)` | Snapshot chứa chính cấu hình tạm thời. | Chụp trước khi thay đổi bất kỳ default nào. |
| Ghi đè ngoại lệ kiểm thử trong `catch` | Báo pass giả dù assertion đã thất bại. | Để lỗi test được ném tiếp; dùng `finally` chỉ để cleanup. |
| Tin `try/finally` giải quyết song song | Race giữa snapshot, mutation và restore. | Khóa các test hợp tác, chạy tuần tự hoặc tách JVM. |
| Gọi `getDefault()` ở cuối để suy ra giá trị cũ | Tại thời điểm đó nó có thể chính là locale tạm. | Dùng snapshot đã lưu. |
| Nghĩ format category đồng nghĩa time zone | Ngày giờ còn phụ thuộc `ZoneId`/`TimeZone`. | Quản lý time zone riêng. |
| Tạo formatter trước khi đổi default | Không chắc formatter cũ phản ánh default mới. | Tạo formatter trong phạm vi thử nghiệm hoặc truyền locale trực tiếp. |

## 10. Bài tập tự luyện

**Bài 1 — Phục hồi sau lỗi:** từ `LocaleDefaultRestoreDemo`, cố ý ném `new AssertionError("simulated failure")` bên trong `try`. Trong một lớp gọi bên ngoài, quan sát rằng exception vẫn được báo, nhưng snapshot của ba locale đã được khôi phục. Không biến lỗi test thành pass.

**Bài 2 — Override category ban đầu:** trước khi chụp snapshot của một phạm vi test khác, thiết lập base `en-US`, DISPLAY `fr-FR` và FORMAT `de-DE`. Trong phạm vi test, gọi `setDefault(Locale.JAPAN)`. Kiểm chứng rằng phục hồi chỉ base làm mất hai override, còn phục hồi đầy đủ giữ lại cả ba. Cuối cùng vẫn phải restore cấu hình gốc của JVM của bài thực hành.

**Bài 3 — Tránh sửa global state:** viết một hàm `formatAmount(BigDecimal amount, Locale locale)` sử dụng `NumberFormat.getNumberInstance(locale)`. Kiểm tra hai locale được truyền trực tiếp; chứng minh `Locale.getDefault()` không đổi trước và sau hai lần gọi.

**Bài 4 — Kiểm soát song song:** thử giải thích lịch thực thi xen kẽ ở mục 7. Sau đó thiết kế quy tắc dùng cùng `@ResourceLock` cho các JUnit test truy cập default locale; nêu giới hạn đối với thread nền không tham gia test framework.

### Checklist hoàn thành

- [ ] Phân biệt `Locale.getDefault()` và hai mặc định theo `DISPLAY`, `FORMAT`.
- [ ] Hiểu tác động `Locale.setDefault(Locale)` lên cả hai category.
- [ ] Chụp ba giá trị **trước** mọi thao tác sửa default.
- [ ] Dùng `finally` và restore theo thứ tự **base → DISPLAY → FORMAT**.
- [ ] Không che giấu assertion failure; có thể tự xác minh trạng thái sau phục hồi.
- [ ] Nhận diện race condition khi nhiều test cùng sửa default của JVM.
- [ ] Biết khi nào nên truyền `Locale` tường minh hoặc cô lập test trong JVM riêng.

Quy tắc cần ghi nhớ: **một test đã thay đổi cấu hình locale toàn JVM phải khôi phục đúng trạng thái đã thấy lúc bắt đầu, kể cả khi kiểm thử thất bại; và nếu chạy song song, mọi test liên quan phải có cơ chế cô lập/phối hợp.**