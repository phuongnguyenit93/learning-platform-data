# Phân biệt thứ tự phiên bản Java với khả năng cung cấp một tính năng

**Chủ đề:** Mô hình phiên bản — Java 10 trở lên.

Một phiên bản Java **mới hơn** theo `Runtime.Version.compareTo(...)` không tự động bảo đảm mọi tính năng mà chương trình kỳ vọng đều **tồn tại, được bật, truy cập được và dùng được**. Đây là hai câu hỏi hoàn toàn khác nhau:

1. **Thứ tự phiên bản:** Hai bản phát hành có thứ tự trước/sau ra sao theo một quy tắc số phiên bản? Ví dụ `10.0.2` và `10.0.10` bản nào mới hơn; `21-ea` và `21` có thứ tự thế nào?
2. **Khả năng thực tế:** Trong **môi trường hiện chạy**, một API, module, tính năng ngôn ngữ hoặc chức năng ứng dụng có sẵn và **có thể sử dụng đúng điều kiện** hay không?

Java có lớp `Runtime.Version` từ Java 9; Java 10 thay mô hình version theo hướng **`FEATURE.INTERIM.UPDATE.PATCH`** và cung cấp các accessor `feature()`, `interim()`, `update()`, `patch()`. Những API này vẫn hiện hành, trong khi các accessor `major()`, `minor()`, `security()` đã **deprecated từ Java 10**; hãy dùng tên mới. Quan trọng: chữ **`FEATURE` trong số phiên bản là bộ đếm bản phát hành**, **không phải danh sách các capability của bản Java đó**.

Bài này giải thích cách sắp xếp phiên bản đúng, khi nào dùng `feature()` như điều kiện tương thích, khi nào cần kiểm tra API/module/method thật, khác biệt giữa **thời điểm biên dịch** và **thời điểm chạy**, cùng phương pháp thiết kế fallback. Năm chương trình Java thuần đã được biên dịch bằng `javac --release 10` và chạy kiểm chứng; còn một đoạn mã dùng API Java 11 được cố ý thử biên dịch với `--release 10` để xác nhận lỗi đúng dự kiến.

## 1. Hai câu hỏi cần được tách rời

Giả sử một ứng dụng cần gọi tính năng tên `Feature X`:

~~~text
Câu hỏi A — THỨ TỰ PHIÊN BẢN
Java đang chạy là 17.0.12 hay 21.0.2?
Có >= một mốc phiên bản đã quy định không?

Câu hỏi B — KHẢ NĂNG DÙNG TÍNH NĂNG
Feature X có thật sự trong runtime image không?
Lớp/method/module có được truy cập không?
Đã bật cờ cần thiết chưa?
Có dependency/provider/nền tảng phù hợp không?
Code có được biên dịch đúng phiên bản API không?
~~~

Một lần kiểm tra `Runtime.version().feature() >= 11` chỉ giải đáp **một phần của câu hỏi A**. Nó không kiểm tra xem class mà chương trình cần có trong một runtime bị rút gọn bằng `jlink`, module đã được resolve, thư viện bên thứ ba đã được cài, hoặc cấu hình runtime có bật chức năng hay không.

### Bảng phân biệt

| Khái niệm | Kiểm tra như thế nào? | Kết luận được phép |
| --- | --- | --- |
| **Phiên bản đang chạy** | `Runtime.version()` | Biết bản Java runtime được khai báo |
| **Thứ tự hai phiên bản Java** | `Runtime.Version.compareTo(...)` | Phiên bản nào được xếp trước/sau theo hợp đồng của lớp |
| **Đếm feature release** | `Runtime.version().feature()` | Biết số hiệu feature release, ví dụ 17, 21 |
| **API Java SE được hỗ trợ khi biên dịch** | `javac --release N` | Kiểm tra cú pháp, bytecode target và API công khai theo release N |
| **Một module có trong runtime image** | `ModuleFinder.ofSystem().find(name)` | Module hệ thống có trong image này |
| **Một module đã resolve vào boot layer** | `ModuleLayer.boot().findModule(name)` | Module có mặt trong boot layer |
| **Một lớp/method có thể được tìm thấy** | `Class.forName` hoặc reflection | Kiểm chứng được lớp/method trong hoàn cảnh class loader hiện tại; **chưa bảo đảm mọi lời gọi hoạt động** |
| **Feature có dùng được theo nghiệp vụ?** | Capability check + cấu hình + thử hành vi + kiểm thử tích hợp | Chỉ kết luận trong phạm vi những điều kiện đã kiểm tra |

**Không thay thế một capability check cụ thể bằng so sánh chuỗi `java.version`.** So sánh phiên bản có chỗ dùng chính đáng, nhưng phải nói rõ nó đang trả lời câu hỏi nào.

## 2. Mô hình phiên bản Java từ Java 10 còn áp dụng hiện nay

Java 10 bắt đầu mô hình phát hành theo thời gian. `Runtime.Version` mô tả số phiên bản như:

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

Các thành phần mang ý nghĩa:

- **`FEATURE`:** bộ đếm phiên bản phát hành tính năng, tăng theo chu kỳ phát hành, **không phải số lượng tính năng**; một feature release có thể thêm tính năng, thay đổi hành vi hoặc loại bỏ API theo chính sách đã công bố.
- **`INTERIM`:** dành cho bản phát hành trung gian có sửa lỗi/cải tiến tương thích, không phải một feature release.
- **`UPDATE`:** bản cập nhật sửa lỗi, bảo mật hoặc regression trong cùng dòng feature release.
- **`PATCH`:** bản vá khẩn cấp cho vấn đề quan trọng.
- Ngoài bốn thành phần này, một implementation có thể có thành phần bổ sung; một version string cũng có thể mang **pre-release**, **build number** và **optional build information**.

Không viết `Runtime.Version.major()`, `minor()` hoặc `security()` trong mã mới: chúng là các tên cũ đã deprecated từ Java 10. Dùng `feature()`, `interim()`, `update()`, `patch()`.

Ví dụ bản `17.0.12+7`:

| API | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `feature()` | 17 | Feature-release counter |
| `interim()` | 0 | Interim counter |
| `update()` | 12 | Update counter |
| `patch()` | 0 | Không có patch element khác 0 |
| `build()` | `Optional.of(7)` | Build number |
| `version()` | `[17, 0, 12]` | Danh sách số thành phần; không tự thêm số 0 ở cuối |
| `pre()` | `Optional.empty()` | Không phải pre-release theo string đã parse |

Các bộ đếm bằng 0 ở **cuối** không cần có mặt trong dạng string. Ví dụ `17.0.12` có `patch()==0` mà không cần viết `17.0.12.0`. Khi parse, dùng đúng **cú pháp của `Runtime.Version`**, không tự giả định mọi chuỗi nhãn sản phẩm hoặc tên JAR là một version Java hợp lệ.

### `Runtime.Version` là lớp mô tả version, không là danh mục tính năng

`Runtime.Version` là **value-based class**: không dùng `==` để so sánh identity hai instance, không đồng bộ hóa trên object này hoặc dựa vào identity hash code. So sánh nội dung bằng `equals`/`compareTo`. Nó mô tả **thứ tự và metadata version**, không đi tra danh sách API đang được cài đặt.

`Runtime.version()` trả phiên bản của **Java runtime đang chạy process hiện tại**. Nếu chương trình chạy trong container hoặc một custom runtime image, đó là runtime bên trong container/image, không phải bản JDK được cài ở một terminal khác hoặc bản Java IDE đang dùng để build.

## 3. So sánh phiên bản phải theo thành phần số, không theo từ điển

Một lỗi phổ biến:

~~~java
// SAI nếu dùng String để so thứ tự phiên bản:
boolean newer = "10.0.2".compareTo("10.0.10") > 0;
~~~

Đây là đoạn minh họa trong method. `String.compareTo` là so sánh **từ điển từng ký tự**, nên nó cho rằng `"10.0.2"` lớn hơn `"10.0.10"` do ký tự `'2'` lớn hơn `'1'`. Nhưng `2 < 10` ở thành phần update.

Đúng với version Java:

~~~java
Runtime.Version oldVersion = Runtime.Version.parse("10.0.2");
Runtime.Version newVersion = Runtime.Version.parse("10.0.10");

boolean correct = oldVersion.compareTo(newVersion) < 0; // true
~~~

`Runtime.Version.compareTo` so sánh các thành phần version **theo số**, rồi xét các thông tin pre-release, build và optional theo hợp đồng lớp.

### Thứ tự của metadata cũng cần được hiểu đúng

Quy tắc thứ tự tổng quát của `Runtime.Version.compareTo`:

1. Dãy số version được xét trước và so sánh số học từng thành phần.
2. Khi cùng dãy số, **pre-release** (ví dụ `21-ea`) được xếp **trước** phiên bản không có pre-release (ví dụ `21`).
3. Khi các phần tương ứng bằng nhau, **build number** cũng tham gia so sánh, chẳng hạn `21+1 < 21+2`.
4. **Optional build information** tham gia vào `compareTo` thường; nhưng có thể **bỏ qua** bằng `compareToIgnoreOptional`.
5. Dùng `equals` đi với `compareTo`; dùng `equalsIgnoreOptional` đi với `compareToIgnoreOptional` nếu chủ ý bỏ qua trường optional.

**Một build number lớn hơn không phải bằng chứng rằng mọi tính năng đã sẵn sàng hơn.** Nó chỉ được xếp sau trong quy tắc comparison. Tương tự, `21-ea` có `feature()==21` nhưng là **early access**, không nên mặc định có cùng mức độ ổn định/chính sách triển khai như `21` chính thức.

### Chương trình chạy được 1 — So sánh thứ tự phiên bản đúng

Lưu **`VersionOrderingDemo.java`**:

~~~java
public class VersionOrderingDemo {
    public static void main(String[] args) {
        Runtime.Version a = Runtime.Version.parse("10.0.2");
        Runtime.Version b = Runtime.Version.parse("10.0.10");
        System.out.println("numeric-order=" + (a.compareTo(b) < 0));
        System.out.println("lexical-wrong=" +
                ("10.0.2".compareTo("10.0.10") > 0));

        Runtime.Version early = Runtime.Version.parse("21-ea");
        Runtime.Version finalRelease = Runtime.Version.parse("21");
        System.out.println("early-before-final=" +
                (early.compareTo(finalRelease) < 0));

        Runtime.Version build1 = Runtime.Version.parse("21+1");
        Runtime.Version build2 = Runtime.Version.parse("21+2");
        System.out.println("build-order=" +
                (build1.compareTo(build2) < 0));
        System.out.println("same-feature=" +
                (build1.feature() == build2.feature()));

        Runtime.Version optionalA =
                Runtime.Version.parse("17.0.2+8-alpha");
        Runtime.Version optionalB =
                Runtime.Version.parse("17.0.2+8-beta");
        System.out.println("compare-optional=" +
                (optionalA.compareTo(optionalB) < 0));
        System.out.println("ignore-optional=" +
                (optionalA.compareToIgnoreOptional(optionalB) == 0));
        System.out.println("equals-optional=" +
                optionalA.equals(optionalB));
        System.out.println("equals-ignore-optional=" +
                optionalA.equalsIgnoreOptional(optionalB));
    }
}
~~~

Chạy bằng một JDK hỗ trợ `--release 10`:

~~~bash
javac --release 10 VersionOrderingDemo.java
java VersionOrderingDemo
~~~

**Stdout chính xác:**

~~~text
numeric-order=true
lexical-wrong=true
early-before-final=true
build-order=true
same-feature=true
compare-optional=true
ignore-optional=true
equals-optional=false
equals-ignore-optional=true
~~~

Những kết quả quan trọng:

- `numeric-order=true` trong khi `lexical-wrong=true`: cách so sánh chuỗi trực tiếp cho **kết luận ngược** so với version số.
- `early-before-final=true`: khi số version bằng nhau, pre-release được xếp trước release chính thức.
- `build-order=true` nhưng `same-feature=true`: thứ tự bản build có thể khác mà bộ đếm feature release **không đổi**.
- `compare-optional=true` khác `ignore-optional=true`: phải nói rõ ứng dụng **có xét** trường optional build metadata hay không.
- `equals-optional=false` nhưng `equals-ignore-optional=true`: không dùng `equals` rồi so sánh với logic bỏ optional ở nơi khác, vì tạo ra tiêu chí không nhất quán.

Nếu ứng dụng muốn so sánh đúng **số feature release** mà thôi, `a.feature() >= b.feature()` có thể phù hợp hơn `a.compareTo(b) >= 0`. Ví dụ hai runtime `21+1` và `21+2` **cùng một mức feature** dù `compareTo` có thứ tự khác.

## 4. Đọc các thành phần qua API Java 10, không đoán từ `java.version`

Có hai kiểu câu hỏi:

- “Runtime đang ở feature release bao nhiêu?” → `Runtime.version().feature()`.
- “Chuỗi version này có update/build/pre-release nào?” → `Runtime.Version.parse(...)` rồi dùng các getter tương ứng.

Việc tự chia chuỗi bằng `split("\\.")` có nhiều vấn đề: dấu `-ea`, dấu `+` và optional metadata không thuộc phần số; ngoài ra cập nhật tương thích có thể thêm các thành phần. Dùng parser của Java đúng mục đích sẽ rõ ràng hơn.

### Chương trình chạy được 2 — Thành phần phiên bản

Lưu **`VersionPartsDemo.java`**:

~~~java
public class VersionPartsDemo {
    public static void main(String[] args) {
        Runtime.Version version =
                Runtime.Version.parse("17.0.12+7");

        System.out.println("feature=" + version.feature());
        System.out.println("interim=" + version.interim());
        System.out.println("update=" + version.update());
        System.out.println("patch=" + version.patch());
        System.out.println("build=" + version.build().orElse(-1));
        System.out.println("elements=" + version.version());
        System.out.println("pre-absent=" + !version.pre().isPresent());

        Runtime.Version early = Runtime.Version.parse("21-ea+5");
        System.out.println("early-pre=" + early.pre().orElse("none"));
        System.out.println("early-build=" + early.build().orElse(-1));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 VersionPartsDemo.java
java VersionPartsDemo
~~~

**Stdout chính xác:**

~~~text
feature=17
interim=0
update=12
patch=0
build=7
elements=[17, 0, 12]
pre-absent=true
early-pre=ea
early-build=5
~~~

Đoạn này minh họa **cấu trúc version**, không kiểm tra bất kỳ API nào có trong runtime. Một phiên bản có `update()==12` không nói gì trực tiếp về việc “tính năng X đã bật”; nó chỉ mô tả một thành phần số.

### Tránh các API deprecated từ Java 10

~~~java
int release = Runtime.version().feature(); // nên dùng
// int legacy = Runtime.version().major(); // deprecated từ Java 10
~~~

Đây là đoạn trong method; dòng thứ hai được **comment** để không dùng API deprecated trong code mới. Lý do đổi tên: phần đầu tiên là bộ đếm **feature release**, không nên diễn giải theo nhãn `major/minor/security` cũ.

## 5. Thứ tự phiên bản không phải chứng minh khả năng cung cấp tính năng

Một phép so sánh version chỉ xác định rằng **runtime được báo cáo là phiên bản N hoặc lớn hơn**. Để một tính năng hoạt động, thường phải đồng thời đáp ứng:

| Điều kiện cần | Ví dụ | Cách xác minh thực tế |
| --- | --- | --- |
| **Mốc Java/API** | API chuẩn công bố từ Java 11 | Đối chiếu Javadoc/JEP; kiểm tra mức `feature` nếu cần |
| **Môi trường biên dịch** | Code dùng API Java 11 nhưng target Java 10 | Biên dịch với `javac --release 10` để phát hiện |
| **Runtime image** | Module `java.net.http` có thể bị lược khỏi một custom image | Dùng `ModuleFinder.ofSystem()` hoặc xem cấu hình image |
| **Module đã được resolve** | Module có trong image nhưng chưa ở boot layer | `ModuleLayer.boot().findModule(...)` hoặc cơ chế resolution phù hợp |
| **Class/method xuất hiện** | `String.isBlank()` từ Java 11 | Reflection, kiểm tra Javadoc và thực thi hành vi cần thiết |
| **Cấu hình/flag** | Một tính năng preview hoặc chức năng bị quản trị viên tắt | Kiểm tra chế độ bật, cờ khởi động và policy tương ứng |
| **Phụ thuộc bên ngoài** | JDBC driver, provider, native library, server | Kiểm tra provider/dependency và test thực tế |
| **OS/kiến trúc** | Tính năng native hoặc thư viện liên kết theo nền tảng | Kiểm tra OS/arch/runtime library và môi trường triển khai |
| **Hợp đồng sản phẩm** | Feature flag của ứng dụng đã tắt | Kiểm tra cấu hình nghiệp vụ, quyền truy cập, rollout |
| **Mức độ tương thích/bảo mật** | Một bản vá bug hay CVE | Đối chiếu bản build, vendor advisory và xác minh patch liên quan |

**Dấu `>=` version chỉ là một dữ kiện, không phải điều kiện đầy đủ.** Trong nhiều trường hợp, ứng dụng nên ưu tiên **thử đúng API/capability cần dùng** hoặc khai báo **yêu cầu runtime tối thiểu** trong build và deployment, thay vì rải nhiều nhánh kiểm tra số phiên bản.

### Ví dụ về tiêu chuẩn API khác với capability tùy chọn

`java.net.http.HttpClient` trở thành API chuẩn trong module `java.net.http` ở Java 11 (JEP 321). Một JDK runtime đầy đủ và được cấu hình bình thường ở bản Java mới có thể cung cấp API này; nhưng với một custom runtime image chỉ giữ các module cần thiết, không nên chỉ đọc số `feature` rồi kết luận module **chắc chắn đã có và được resolve**.

Tương tự, `String.isBlank()` có từ Java 11. Nếu source code **phải biên dịch tương thích Java 10**, nó **không được gọi trực tiếp API Java 11** ngay cả khi có nhánh `if (Runtime.version().feature() >= 11)`; trình biên dịch vẫn kiểm tra mọi lời gọi method được viết trong source.

## 6. Thời điểm biên dịch khác với thời điểm chạy

Khi build với một JDK mới nhưng muốn ứng dụng chạy trên Java 10, hãy dùng:

~~~bash
javac --release 10 MyApp.java
~~~

`--release 10` (trên JDK còn hỗ trợ target đó) yêu cầu compiler:

1. Kiểm tra cú pháp Java theo phiên bản đích.
2. Xuất class file dành cho phiên bản đích.
3. Biên dịch dựa trên **API công khai có trong release đích**, không vô tình dùng API chỉ xuất hiện ở JDK đang build.

`--source 10 --target 10` riêng lẻ **không phải thay thế đầy đủ** cho `--release 10` về việc giới hạn API nền tảng theo release đích. Hãy dùng `--release` khi cần kiểm tra API của Java 10 một cách nhất quán.

**Ví dụ cố ý không biên dịch với `--release 10`:**

~~~java
public class NewApiCompileFailure {
    public static void main(String[] args) {
        if (Runtime.version().feature() >= 11) {
            System.out.println(" ".isBlank());
        }
    }
}
~~~

Đây là **đoạn minh họa lỗi biên dịch**, không phải chương trình runnable Java 10. `String.isBlank()` được giới thiệu từ **Java 11**. Lệnh:

~~~bash
javac --release 10 NewApiCompileFailure.java
~~~

**Kết quả mong đợi:** `javac` kết thúc với mã lỗi khác 0 và báo không tìm được method `isBlank()` đối với `String` trong API Java 10. Thử nghiệm đã xác nhận lỗi đúng dự kiến.

**Vì sao nhánh `if` không cứu được?** Trình biên dịch phải xác minh ký hiệu method trước khi chương trình có thể chạy. Nó không chờ runtime kiểm tra điều kiện rồi mới quyết định có biên dịch nhánh đó hay không.

Để hỗ trợ nhiều Java release, lựa chọn tốt thường là:

- Giữ **một baseline Java** được quy định và chỉ gọi các API có trong baseline đó.
- Dùng thư viện/adapter tương thích baseline hoặc **multi-release JAR** khi có nhu cầu thật và thiết kế/test đúng.
- Với tính năng tùy chọn chỉ tồn tại ở runtime mới, có thể dùng một **adapter phản chiếu** hoặc cơ chế plugin/service, nhưng phải cân nhắc bảo trì, lỗi linking và quyền truy cập. Không biến reflection thành phương án mặc định cho mọi API.
- Nếu ứng dụng thực sự yêu cầu Java 11+, hãy tăng baseline dự án và kiểm tra môi trường triển khai, thay vì viết những nhánh version check làm người dùng hiểu rằng vẫn hỗ trợ Java 10.

## 7. Kiểm tra module, class và method thay vì chỉ kiểm tra số Java

Trong hệ module Java 9+, có thể có sự khác biệt giữa **module nằm trong runtime image** và **module đã có trong boot layer**:

- `ModuleFinder.ofSystem().find("java.net.http")`: tìm module trong **runtime image hiện tại**. Một image `jlink` cắt gọn có thể không có module này.
- `ModuleLayer.boot().findModule("java.net.http")`: hỏi module đã được **resolve trong boot layer** chưa. Image có module nhưng module chưa được resolve vào layer đang xét thì hai kết quả có thể khác nhau.
- `Class.forName(name, false, loader)`: thử tìm/tải **một class** với loader đã chọn mà không yêu cầu initialize class ngay (khi `initialize=false`). Nó không bảo đảm mọi method trong class đều callable, mọi provider đã được nạp hay cấu hình đã đúng.
- `Class.getMethod(name, ...)`: có thể kiểm tra một **public method signature** cụ thể. Việc một method tồn tại không phải bằng chứng toàn bộ một tính năng nghiệp vụ chạy thành công.

### Chương trình chạy được 3 — Capability probe bằng API Java 10

Lưu **`ApiAvailabilityDemo.java`**:

~~~java
import java.lang.module.ModuleFinder;

public class ApiAvailabilityDemo {
    static boolean visibleClass(String className) {
        try {
            Class.forName(className, false,
                    ClassLoader.getPlatformClassLoader());
            return true;
        } catch (ClassNotFoundException | LinkageError ex) {
            return false;
        }
    }

    static boolean hasPublicMethod(Class<?> owner, String method) {
        try {
            owner.getMethod(method);
            return true;
        } catch (NoSuchMethodException ex) {
            return false;
        }
    }

    public static void main(String[] args) {
        System.out.println("runtime-at-least-10=" +
                (Runtime.version().feature() >= 10));
        System.out.println("http-module-in-image=" +
                ModuleFinder.ofSystem()
                        .find("java.net.http").isPresent());
        System.out.println("http-module-in-boot-layer=" +
                ModuleLayer.boot()
                        .findModule("java.net.http").isPresent());
        System.out.println("http-api-class-visible=" +
                visibleClass("java.net.http.HttpClient"));
        System.out.println("string-isBlank-method=" +
                hasPublicMethod(String.class, "isBlank"));
        System.out.println("invented-class-visible=" +
                visibleClass("java.example.NoSuchCapability"));
    }
}
~~~

Biên dịch với **API Java 10** và chạy trên JDK kiểm thử (JDK 24.0.2):

~~~bash
javac --release 10 ApiAvailabilityDemo.java
java ApiAvailabilityDemo
~~~

**Stdout đúng trong môi trường kiểm thử:**

~~~text
runtime-at-least-10=true
http-module-in-image=true
http-module-in-boot-layer=true
http-api-class-visible=true
string-isBlank-method=true
invented-class-visible=false
~~~

Điều chương trình chứng minh:

1. Code **biên dịch theo Java 10** vì chỉ trực tiếp dùng `ModuleFinder`, `ModuleLayer`, reflection và `Runtime.Version.feature()` đã có trong API target; nó không trực tiếp tham chiếu kiểu `java.net.http.HttpClient` hoặc gọi `String.isBlank()` lúc biên dịch.
2. Trên JDK 24 đầy đủ ở môi trường chạy, module `java.net.http` được phát hiện trong image và boot layer, class có thể được tìm qua platform class loader, và method `isBlank` được nhìn thấy qua reflection.
3. Ở một runtime Java 10, các kiểm tra cho API Java 11 có thể trả false; ở một custom runtime mới bị cắt module, `in-image`/`in-boot-layer` cũng có thể khác. **Không sao chép nguyên stdout của JDK 24 thành dự đoán bắt buộc trên mọi runtime**.
4. Tên class không tồn tại được xử lý như một capability không sẵn có trong phép thăm dò cụ thể.
5. `Class.forName` với `initialize=false` không tự biến việc class tồn tại thành cam kết phương thức có thể gọi thành công.

**Giới hạn cố ý của demo:** dùng reflection và class loader không chứng minh rằng mọi quyền truy cập, dependency bên thứ ba, giới hạn bảo mật hoặc cấu hình chức năng đã thỏa. Với một API nghiệp vụ cụ thể, hãy thử đúng đường sử dụng cần thiết trong môi trường kiểm thử tích hợp và xử lý lỗi thích hợp. Không bắt đại mọi `Throwable` rồi âm thầm giả định có thể fallback; lỗi nghiêm trọng có thể cần dừng thay vì che đi.

## 8. Mô hình điều kiện kép: mốc phiên bản + capability + cấu hình

Một chức năng có thể có **mốc phiên bản tối thiểu**, nhưng chỉ nên được bật nếu các điều kiện độc lập đều đúng:

~~~text
CAN_USE_FEATURE =
    runtime_feature_release >= minimum_release
    AND required_API_or_provider_present
    AND feature_enabled_by_configuration
    AND permission_and_platform_requirements_met
~~~

Đây là **mô hình logic minh họa**, không phải chữ ký API có sẵn. Trong ứng dụng thực tế, có thể có nhiều điều kiện hơn. Đặc biệt, **feature flag** của sản phẩm không liên quan đến bộ đếm `Runtime.Version.feature()` dù trùng từ “feature”.

### Chương trình chạy được 4 — Chứng minh “mới hơn” vẫn không đủ

Lưu **`FeatureDecisionDemo.java`**:

~~~java
public class FeatureDecisionDemo {
    static boolean canUse(Runtime.Version runtime,
                          int minimumFeature,
                          boolean apiPresent,
                          boolean enabled) {
        return runtime.feature() >= minimumFeature
                && apiPresent && enabled;
    }

    public static void main(String[] args) {
        Runtime.Version newer = Runtime.Version.parse("25");
        Runtime.Version older = Runtime.Version.parse("10");

        System.out.println("newer-but-api-missing=" +
                canUse(newer, 11, false, true));
        System.out.println("newer-but-disabled=" +
                canUse(newer, 11, true, false));
        System.out.println("older-than-minimum=" +
                canUse(older, 11, true, true));
        System.out.println("all-conditions-met=" +
                canUse(newer, 11, true, true));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 FeatureDecisionDemo.java
java FeatureDecisionDemo
~~~

**Stdout chính xác:**

~~~text
newer-but-api-missing=false
newer-but-disabled=false
older-than-minimum=false
all-conditions-met=true
~~~

**Giới hạn của ví dụ:** `25` và `10` là **version mô phỏng qua `parse`**, không phải kết luận về JDK thực tế trên máy. Các giá trị `apiPresent` và `enabled` được truyền vào để biểu diễn capability/configuration độc lập. Đây là **mô hình kiểm thử chính sách**: chứng minh về mặt logic rằng ngay cả số version đủ mới cũng **không cứu được** tình huống API vắng mặt hoặc chức năng bị tắt.

Với ứng dụng thật, nguồn `apiPresent` không nên là boolean do developer đoán. Hãy nối nó với cách phát hiện API/module/provider đã được thiết kế; nguồn `enabled` phải đến từ cấu hình/feature flag có thẩm quyền. Test riêng các trường hợp **version cao nhưng API thiếu**, **API có nhưng flag tắt**, và **version thấp nhưng cờ bật** để tránh false positive.

## 9. Khi nào chỉ cần check `feature()`?

Check version **không sai**; nó sai khi bị dùng như **chứng minh đầy đủ** cho khả năng dùng mọi tính năng. Những trường hợp thích hợp:

- **Fail fast với minimum JDK:** chương trình/installer yêu cầu tối thiểu một feature release rõ ràng đã xác định, có thể kiểm tra và thông báo “Java runtime quá cũ”.
- **Telemetry/diagnostics:** ghi nhận feature release, vendor và runtime build để phân tích sự cố, kết hợp dữ liệu module và cấu hình khác.
- **Chọn đường tương thích đã được kiểm thử:** một nhánh code chỉ dùng các API có trong compile baseline, hoặc các adapter được đóng gói theo đúng môi trường thực thi.
- **Phân tích/so sánh bản Java:** sắp xếp danh sách `Runtime.Version` theo đúng thành phần số, pre-release và build.

### Chương trình chạy được 5 — Guard đúng phạm vi

Lưu **`VersionGateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VersionGateDemo {
    static boolean supportsGeneralApi(int minimumFeature) {
        return Runtime.version().feature() >= minimumFeature;
    }

    public static void main(String[] args) {
        Runtime.Version now = Runtime.version();

        System.out.println("runtime-version-parses=" +
                Runtime.Version.parse(now.toString()).equals(now));
        System.out.println("feature-at-least-10=" +
                supportsGeneralApi(10));

        List<String> values = new ArrayList<>();
        values.add("java");
        System.out.println("fallback-result=" + values.get(0));

        System.out.println("min-1000=" +
                supportsGeneralApi(1000));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 VersionGateDemo.java
java VersionGateDemo
~~~

**Stdout đúng trong môi trường JDK 24.0.2:**

~~~text
runtime-version-parses=true
feature-at-least-10=true
fallback-result=java
min-1000=false
~~~

`supportsGeneralApi` có tên mang tính mô tả, nhưng kết quả thực tế **chỉ phản ánh điều kiện số feature release**. Không nên lấy tên hàm hoặc `true` từ hàm đó làm bảo đảm rằng một API có sẵn; nếu cần, đặt tên rõ hơn như `runtimeFeatureAtLeast(...)`. Trong ví dụ, hành vi `ArrayList` là logic fallback có sẵn từ lâu, không phụ thuộc vào một API Java mới.

`min-1000=false` chỉ dùng một mốc giả định đủ cao để cho thấy phép guard hoạt động với JDK kiểm thử, **không phải khẳng định Java sẽ không bao giờ đạt tới số 1000**.

## 10. Những nguồn khiến version cao nhưng capability vẫn thiếu

### A. Runtime image đã được tối giản

`jlink` có thể tạo một runtime chỉ gồm các module cần thiết. Hai image có thể thuộc cùng feature release nhưng khác tập module, dẫn tới việc `ModuleFinder.ofSystem().find("...")` trả kết quả khác nhau. Khi viết ứng dụng module-aware, cần xác minh cả module có trong image và module được resolve trong layer/cấu hình đang dùng.

### B. Preview/incubating/experimental feature

Một số tính năng ngôn ngữ hoặc API trong các bản Java hiện đại có thể đang ở trạng thái **preview/incubator** theo từng release và cần cờ tương ứng như `--enable-preview`, module đặc biệt hoặc chính sách build/runtime. **`feature() >= N` không tự bật preview** và không hứa tên/lược đồ API thử nghiệm duy trì qua các release.

Cần tra **JEP của tính năng cụ thể**, trạng thái final/preview/incubating ở release đích, yêu cầu compiler/runtime và kiểm thử phiên bản đó. Không dùng một mốc Java rồi suy diễn mọi preview feature của version ấy đều là API ổn định hiện nay.

### C. Runtime và compile target khác nhau

Một ứng dụng build bằng JDK 24 với `--release 10` chỉ được phép trực tiếp dùng API Java 10 ở source. Nếu muốn dùng API Java 11+ cần tăng baseline hoặc thiết kế một adapter optional có kiểm thử, không thêm `if(feature>=11)` quanh lời gọi không biên dịch được.

Ngược lại, việc source build được cho `--release 10` **không chứng minh** runtime Java 10 nào đó có mọi dependency, module tùy chọn hoặc cài đặt nhà cung cấp mà ứng dụng cần. Đây là hai bài kiểm tra khác nhau.

### D. Tính năng được cấu hình hoặc có quyền truy cập

Tính năng phụ thuộc backend, giấy phép, feature flag, quyền người dùng hoặc network có thể bị tắt hoàn toàn độc lập với JDK. Runtime version chỉ phục vụ theo dõi tương thích nền tảng, không là nguồn xác thực quyền sử dụng.

### E. API thay đổi, lỗi bị sửa hoặc được backport

Một số bản phát hành mới có thể loại bỏ tính năng cũ hoặc thay đổi hành vi theo quy trình phát triển của Java; các bản cập nhật/vendor cũng có thể đưa bản vá vào dòng hỗ trợ trước. Vì vậy:

- “Java mới hơn” không có nghĩa **tất cả API cũ đều còn nguyên**, đặc biệt với API nội bộ, thử nghiệm hoặc đã bị loại bỏ.
- “Có update number lớn hơn” không tự chứng minh **một CVE cụ thể đã được vá**; cần đối chiếu security advisory và build/vendor thực tế.
- Không dùng `Runtime.Version.compareTo` để so một dependency bên thứ ba như `lib-x 2.5.1` với `lib-y 4.0` hoặc áp quy tắc Java lên hệ thống SemVer khác. Mỗi hệ thống version có chính sách riêng.

## 11. `compareTo` và `compareToIgnoreOptional` không phải feature detection

Đây là một nguồn nhầm lẫn tinh tế trong hệ thống upgrade:

~~~java
Runtime.Version a = Runtime.Version.parse("17.0.2+8-alpha");
Runtime.Version b = Runtime.Version.parse("17.0.2+8-beta");

boolean fullOrder = a.compareTo(b) < 0;           // true
boolean sameWithoutOpt = a.equalsIgnoreOptional(b); // true
~~~

Hai dòng trên là đoạn minh họa trong method. **Cả hai** vẫn có cùng `feature()==17`, `update()==2` và `build()==8`. Sự khác nhau nằm ở **optional build metadata** được đưa vào quy tắc so sánh, không phải một lời hứa rằng bản nào có thêm API, provider hoặc tính năng nghiệp vụ.

Lưu ý:

- `compareToIgnoreOptional` chỉ bỏ qua **trường optional**; nó **không** bỏ qua số version, pre-release hay build number.
- `equalsIgnoreOptional` là phép so tương ứng khi cố ý bỏ qua optional; `equals` vẫn phân biệt hai version đầy đủ.
- Nếu cần kiểm tra “đã đạt feature release N” thì dùng `feature()` hoặc logic release tối thiểu phù hợp, không kiểm tra bằng substring `"17"`.
- Nếu cần kiểm tra “đã đủ bản vá bảo mật X” thì kiểm tra chính xác release note và vendor/build advisory, không chỉ sắp xếp version.
- Nếu cần kiểm tra “đã cài module Y” thì hỏi module/image/loader, không dùng `compareToIgnoreOptional` làm proxy.

## 12. Lưu ý khi làm compatibility/fallback

Một chiến lược tương thích tốt nên rõ ràng hơn một chuỗi điều kiện `if` dựa trên version:

1. **Công bố minimum runtime** trong tài liệu sản phẩm, build pipeline và deployment image.
2. **Sử dụng `--release` khi build cho runtime cũ** và có CI thực sự chạy trên runtime tối thiểu.
3. **Xác định API/module nào bắt buộc**, module nào tùy chọn; nếu bắt buộc bị thiếu, fail fast với thông điệp rõ.
4. **Đưa nhánh optional vào adapter riêng** nếu cần hỗ trợ nhiều JDK; compile baseline của phần chung không được vô tình tham chiếu API mới.
5. **Kiểm tra một capability cụ thể** bằng cơ chế phù hợp: module, class, method, provider, configuration hoặc hành vi; đừng dùng một check chung để suy ra tất cả.
6. **Không nuốt mọi exception khi thử capability**. Một số lỗi cấu hình/linking nên được báo như lỗi deployment thay vì âm thầm dùng fallback khác nghĩa.
7. **Viết contract fallback**: chức năng thay thế có chính xác về ngữ nghĩa không, hay chỉ là suy giảm chấp nhận được? Ví dụ `String.trim()` và `String.isBlank()` không phải hai kiểm tra Unicode whitespace hoàn toàn tương đương.
8. **Kiểm thử cả hai nhánh** bằng các runtime/configuration cần hỗ trợ, không chỉ máy developer đang chạy JDK mới.
9. **Theo dõi trạng thái preview/incubator riêng** với chuẩn API ổn định; không mô tả một công nghệ thử nghiệm như tính năng chắc chắn có ở mọi Java mới hơn.
10. **Theo dõi version và capability riêng trong log**: log phiên bản runtime, vendor, module/flag và điều kiện môi trường giúp điều tra đúng nguyên nhân.

### Những tình huống thiết kế thường gặp

| Câu hỏi | Cách ra quyết định phù hợp |
| --- | --- |
| “Chương trình cần tối thiểu Java 17?” | Khai báo runtime requirement và kiểm tra `Runtime.version().feature()` nếu cần fail fast |
| “Image hiện tại có `java.net.http` không?” | `ModuleFinder.ofSystem().find("java.net.http")`, xét tiếp resolution/access |
| “Method `String.isBlank` có thể được nhìn thấy?” | Reflection hoặc biên dịch trực tiếp với baseline Java 11+ |
| “Source Java 10 có gọi được API thêm từ Java 11 không?” | Không được gọi trực tiếp dưới `javac --release 10`; xem negative test |
| “Một thư viện JDBC có provider được cài không?” | Kiểm tra `ServiceLoader`/driver có thật và thử tạo kết nối trong môi trường test |
| “Tính năng đang bị tắt bởi quản trị viên?” | Kiểm tra cấu hình/feature flag; runtime version không liên quan |
| “Hai JDK 21 build nào mới hơn?” | `Runtime.Version.compareTo` theo hợp đồng; cần hiểu pre/build/optional |
| “JDK 21 có đảm bảo đã vá lỗ hổng cụ thể?” | Không suy ra bằng `feature()==21`; đối chiếu advisory/vendor/build liên quan |
| “Có thể dùng tất cả API từ các release trước?” | Không mặc định; tra tình trạng API/compatibility và chạy test |

## 13. Những ngộ nhận và lỗi phổ biến

| Ngộ nhận | Vì sao không đúng | Hướng xử lý |
| --- | --- | --- |
| “`feature()==21` nghĩa là runtime có đủ mọi tính năng Java 21 ở mọi cấu hình” | Preview/flags, module image và provider có thể khác | Tra JEP/API, kiểm tra capability và cấu hình |
| “`compareTo` trả dương nghĩa là tính năng X được hỗ trợ” | So sánh version metadata, không kiểm tra X | Viết capability probe phù hợp |
| “`10.0.2` lớn hơn `10.0.10` vì so chuỗi ra vậy” | So từ điển không phải so số học | Dùng `Runtime.Version.compareTo` |
| “`21-ea` tương đương hoàn toàn `21` vì feature bằng nhau” | Pre-release có trạng thái khác final | Xét `pre()` và điều kiện release hỗ trợ |
| “Build number càng cao thì API càng nhiều” | Build chỉ là thành phần thứ tự release | Kiểm tra API/documentation cụ thể |
| “`compareToIgnoreOptional` bỏ qua mọi metadata” | Chỉ bỏ qua optional build information | Hiểu rõ pre/build vẫn được so |
| “`Runtime.Version.major()` vẫn là API nên cứ dùng mãi” | Deprecated từ Java 10 | Dùng `feature()` |
| “`if(feature >= 11)` sẽ cho source Java 10 gọi `String.isBlank()`” | Compiler kiểm tra symbol trước runtime | `--release 10`, adapter hoặc nâng baseline |
| “JDK mới luôn có mọi module” | Custom image `jlink` có thể bị lược bớt | Kiểm tra module có trong image/layer |
| “`ModuleFinder.ofSystem()` có module là mọi class đều dùng được” | Module có thể chưa resolve hoặc không thể access phù hợp | Kiểm tra layer/exports/readability/behavior |
| “Reflection tìm được method là chắc chắn call thành công” | Quyền truy cập và thực thi còn điều kiện | Thử hành vi và xử lý lỗi chính xác |
| “`--target 10` đảm bảo không vô tình dùng API Java 11” | `--target` chủ yếu giới hạn bytecode, không thay API signature môi trường | Dùng `--release 10` |
| “Java mới hơn có nghĩa vá bảo mật X” | Cần advisory, version update và vendor cụ thể | Kiểm chứng bản vá thực |
| “Java version ordering giống mọi SemVer dependency” | Mỗi hệ thống version có chính sách riêng | Dùng comparator đúng hệ sinh thái |
| “Nếu feature không dùng được, luôn fallback bằng cách bắt `Throwable`” | Có thể che lỗi nghiêm trọng hoặc tạo sai ngữ nghĩa | Bắt đúng ngoại lệ, báo lỗi deploy hoặc fallback có hợp đồng |

## 14. Checklist QA cho chức năng phụ thuộc phiên bản Java

Trước khi merge một thay đổi có `Runtime.Version` hoặc `Runtime.version()`, kiểm tra:

1. **Mục đích check là gì?** So thứ tự release, kiểm tra minimum JDK hay thực sự phát hiện capability?
2. **Có đang so `String.compareTo` hoặc parse số version thủ công không?** Nếu có, cân nhắc `Runtime.Version.parse`/`compareTo`.
3. **Đã xử lý pre-release và build chưa?** `feature()` không thể thay thế đầy đủ so sánh toàn version.
4. **Có dùng `major/minor/security` deprecated không?** Thay bằng `feature/interim/update` hoặc `patch`.
5. **API được sử dụng bắt đầu từ Java mấy?** Kiểm tra Javadoc `Since` và JEP.
6. **CI có chạy `javac --release N` với N là runtime tối thiểu không?** Nếu không, có nguy cơ dùng nhầm API quá mới.
7. **Mã nguồn có chứa tham chiếu API mới trong nhánh `if` không?** Biên dịch vẫn phải resolve được symbol.
8. **Runtime image có module cần không?** Đã xét custom image/jlink và module resolution?
9. **API/module có đủ để coi feature sẵn sàng không?** Có quyền/cấu hình/provider còn thiếu không?
10. **Đã có test đối với runtime hoặc cấu hình không hỗ trợ tính năng chưa?** Nếu không, fallback khó tin cậy.
11. **Tính năng có thuộc preview/incubator không?** Nếu có, đã xác định cờ, trạng thái release và giới hạn hiện tại chưa?
12. **Khả năng cung cấp tính năng có thể thay đổi mà version không đổi không?** Feature flag, provider hoặc môi trường thường làm được điều đó.
13. **Có phân biệt bản vá bảo mật với feature release không?** Một patch/cve không suy ra từ `feature()`.
14. **Có ghi log đủ version/build/vendor và kết quả capability probe không?** Cần để chẩn đoán deployment.
15. **Một phép so phiên bản có đang được dùng ngoài hệ sinh thái Java không?** Không dùng nhầm `Runtime.Version` để so dependency SemVer tùy ý.

Với bài test, nên có ít nhất ba mức xác nhận: **thứ tự version đúng**, **môi trường compile đúng**, và **hành vi capability đúng**. Chỉ một bài test unit cho comparator chưa đủ để xác nhận ứng dụng chạy trong một custom runtime image.

## 15. Câu hỏi tự kiểm tra

1. `Runtime.Version.compareTo(...)` trả lời “phiên bản nào được xếp sau” hay “API X có tồn tại”?
2. Vì sao `String.compareTo("10.0.10")` trên `"10.0.2"` có thể cho kết quả ngược so với cách so version số?
3. `Runtime.Version.parse("17.0.12+7").feature()` và `update()` lần lượt là bao nhiêu?
4. `Runtime.Version.major()` có nên được sử dụng trong Java 10+ mới không?
5. `Runtime.Version.parse("21-ea").feature()==21` có chứng minh đó là bản phát hành ổn định cuối cùng không?
6. `compareToIgnoreOptional` có bỏ qua cả pre-release và build không?
7. Vì sao `javac --release 10` không chấp nhận gọi trực tiếp `String.isBlank()` dù code đặt trong `if(feature >= 11)`?
8. `ModuleFinder.ofSystem()` và `ModuleLayer.boot()` trả lời cùng một câu hỏi không?
9. Nếu Java feature release là 25 nhưng module cần thiết đã bị loại khỏi runtime image, feature có chắc sử dụng được không?
10. Nếu method tồn tại qua reflection, vì sao vẫn có thể phát sinh lỗi khi dùng thật?
11. Có thể chỉ dùng `feature()` để quyết định CVE cụ thể đã được vá không?
12. Nếu ứng dụng có feature flag đang tắt, version Java mới hơn có tự bật tính năng đó không?
13. Điều kiện “runtime đủ mới” khác gì với “source compile được cho runtime tối thiểu”?
14. Khi so bản Java và bản thư viện dùng SemVer khác nhau, có nên dùng chung một comparator không?

**Đáp án:**

1. Trả lời **thứ tự version**, không phát hiện API.
2. String so ký tự từng vị trí; version cần so thành phần **số**.
3. `feature=17`, `update=12`.
4. Không; `major()` đã deprecated, dùng `feature()`.
5. Không; `pre()` vẫn có `ea`, đây là pre-release.
6. Không; chỉ bỏ qua **optional build information**.
7. Compiler phải resolve symbol trong tất cả nhánh source; `isBlank()` là API Java 11.
8. Không; `ofSystem` tìm module trong runtime image, `boot` tìm module đã resolve trong boot layer.
9. Không.
10. Có thể thiếu quyền/module resolution, phụ thuộc, cờ, provider hoặc điều kiện runtime khác.
11. Không; cần advisory và build/vendor cụ thể.
12. Không.
13. Một bên là kiểm tra version lúc chạy; bên kia là hợp đồng **API và bytecode target** khi build.
14. Không tự động; áp quy tắc version của từng hệ thống.

## 16. Tài liệu chính thức còn áp dụng

- **Oracle Javadoc — `Runtime.Version` (Java 10), `feature/interim/update/patch`, `compareTo`, `compareToIgnoreOptional`:** https://docs.oracle.com/javase/10/docs/api/java/lang/Runtime.Version.html
- **Oracle Javadoc — `Runtime.Version` (Java SE 26), hợp đồng version ordering hiện hành:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html
- **Oracle Javadoc — `Runtime.version()`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html
- **OpenJDK — JEP 322, Time-Based Release Versioning:** https://openjdk.org/jeps/322
- **Oracle `javac` — `--release` và API/bytecode target:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html
- **Oracle Javadoc — `ModuleFinder.ofSystem`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleFinder.html
- **Oracle Javadoc — `ModuleLayer.boot()`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html
- **Oracle Javadoc — `Class.forName`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html
- **Oracle Javadoc — `String.isBlank` (từ Java 11):** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- **OpenJDK — JEP 321, HTTP Client (Standard), Java 11:** https://openjdk.org/jeps/321
- **OpenJDK — JEP 282, jlink: The Java Linker:** https://openjdk.org/jeps/282

**Ghi nhớ:** `Runtime.Version` giúp **đọc và sắp xếp phiên bản Java**; `feature()` là **số hiệu feature release**, không là bằng chứng toàn bộ API hay tính năng đã sẵn sàng. Hãy so version đúng kiểu số, biên dịch theo **runtime tối thiểu** bằng `--release`, và khi một tính năng có thể vắng mặt, kiểm tra **module, class, method, cấu hình và hành vi cần dùng** trong môi trường thật. Một JDK “mới hơn” chỉ là một điều kiện tương thích, không phải lời đảm bảo năng lực tuyệt đối.