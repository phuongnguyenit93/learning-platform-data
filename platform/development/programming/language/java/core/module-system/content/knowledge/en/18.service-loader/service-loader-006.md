# Provider bị lỗi và ServiceConfigurationError

## 1. Mục tiêu

Trong Java Service Provider Interface (SPI), ứng dụng biết đến một kiểu dịch vụ (service), còn các thư viện hoặc module khác cung cấp những lớp triển khai (provider). **ServiceLoader** tìm và khởi tạo các provider tại thời điểm chạy. Cơ chế này giúp ứng dụng mở rộng bằng plugin mà không phải phụ thuộc trực tiếp vào từng lớp triển khai.

Bài này giải thích điều gì xảy ra khi provider được khai báo sai, không thể nạp hoặc không thể khởi tạo; cách **ServiceConfigurationError** xuất hiện; và cách tìm nguyên nhân trong ứng dụng dùng classpath hoặc Java Platform Module System (JPMS).

Sau bài học, bạn có thể:
- Phân biệt trường hợp không tìm thấy provider với trường hợp provider bị lỗi.
- Nhận biết thời điểm ServiceLoader thực sự tìm và khởi tạo provider.
- Tìm lỗi trong file cấu hình SPI, module-info.java, classpath, module path và class loader.
- Bắt và xử lý ServiceConfigurationError ở đúng ranh giới của ứng dụng.

## 2. ServiceLoader tìm provider như thế nào?

Một service thường là interface hoặc abstract class. Provider là lớp cụ thể triển khai hoặc kế thừa service đó. Ví dụ, ứng dụng khai báo service Codec; các thư viện khác có thể cung cấp GzipCodec, ZipCodec hoặc một codec khác.

~~~java
package com.example.spi;

public interface Codec {
    String name();
    byte[] encode(byte[] input);
}
~~~

Ứng dụng yêu cầu ServiceLoader tìm các provider:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

Lời gọi **ServiceLoader.load(...)** tạo một ServiceLoader. Nó thường chưa đọc hết cấu hình và chưa khởi tạo tất cả provider ngay tại dòng này. Việc tìm, nạp lớp và tạo đối tượng diễn ra lười (lazy), khi ứng dụng duyệt iterator hoặc xử lý stream.

Vì vậy, lỗi có thể xuất hiện ở vòng lặp, tại **hasNext()** hoặc **next()**, dù dòng gọi **load()** đã chạy bình thường. Với stream, lỗi có thể xuất hiện ở thao tác nào khiến provider được tìm hoặc nạp; gọi **Provider.get()** sẽ khởi tạo provider.

Cần phân biệt hai tình huống:

- **Không có provider:** đây là kết quả hợp lệ. Iterator hết phần tử; **findFirst()** trả về **Optional.empty()**. Không có ServiceConfigurationError chỉ vì không tìm thấy provider.
- **Có khai báo provider nhưng không thể xử lý khai báo đó:** đây là lỗi cấu hình, nạp hoặc khởi tạo. ServiceLoader có thể ném ServiceConfigurationError.

## 3. ServiceConfigurationError là gì?

**java.util.ServiceConfigurationError** là một lớp con của **java.lang.Error**. JDK ném lỗi này khi có vấn đề trong quá trình tìm, nạp hoặc khởi tạo service provider.

Vì nó kế thừa **Error**, đoạn mã chỉ bắt **Exception** sẽ không bắt được ServiceConfigurationError. Khi ứng dụng cần xử lý lỗi SPI tại một ranh giới rõ ràng, hãy bắt chính xác loại lỗi này:

~~~java
try {
    for (Codec codec : ServiceLoader.load(Codec.class)) {
        System.out.println(codec.name());
    }
} catch (ServiceConfigurationError error) {
    error.printStackTrace();
    throw new IllegalStateException(
        "Không thể nạp một Codec provider", error
    );
}
~~~

Không nên bắt mọi **Error** hoặc **Throwable** chỉ để bỏ qua lỗi. Một provider lỗi có thể làm ứng dụng thiếu chức năng quan trọng hoặc khiến kết quả chạy không đáng tin cậy. Hãy quyết định rõ ứng dụng sẽ dừng, dùng implementation mặc định, hay vô hiệu hóa một plugin tùy chọn.

ServiceConfigurationError có constructor nhận message và constructor nhận cả message lẫn cause. Khi lỗi có nguyên nhân gốc, hãy giữ lại exception chain bằng cách log toàn bộ stack trace hoặc kiểm tra **getCause()**. Message thường giúp nhận ra tên service/provider, nhưng cause mới có thể chỉ ra lỗi cụ thể như constructor ném exception hoặc thiếu dependency.

## 4. Các nguyên nhân thường gặp trên classpath

Với ứng dụng dùng classpath, provider được đăng ký bằng một provider-configuration file trong thư mục **META-INF/services**.

Tên file là tên đầy đủ của service. Mỗi dòng chứa tên lớp provider đầy đủ (binary name), ví dụ:

~~~text
META-INF/services/com.example.spi.Codec
~~~

Nội dung:

~~~text
com.example.impl.GzipCodec
com.example.impl.ZipCodec
~~~

Provider có thể nằm trong cùng JAR với file cấu hình hoặc trong một JAR khác, miễn là class loader được dùng để tìm provider có thể nhìn thấy lớp đó.

Các lỗi phổ biến:

1. **Sai tên hoặc sai vị trí file cấu hình.** Tên file phải khớp tên đầy đủ của service, và file phải nằm dưới META-INF/services ở gốc tài nguyên của JAR.
2. **Sai tên lớp provider.** Dòng cấu hình phải là tên lớp đầy đủ, phân biệt chữ hoa/chữ thường; không ghi tên file .java hay đường dẫn thư mục.
3. **File cấu hình sai định dạng.** File phải dùng UTF-8. Mỗi provider nằm trên một dòng; khoảng trắng/tab ở đầu và cuối dòng, dòng trống và phần comment bắt đầu bằng # được bỏ qua. Khai báo trùng lặp được bỏ qua.
4. **Không nạp được lớp provider.** JAR chứa provider không có trên runtime classpath, tên lớp sai, hoặc một dependency mà provider cần bị thiếu.
5. **Provider không triển khai service.** Lớp được khai báo phải thực sự assignable với kiểu service mà ServiceLoader đang dùng.
6. **Không có provider constructor hợp lệ.** Provider trên classpath phải là lớp public, không phải inner class, và có public constructor không tham số để ServiceLoader tạo instance.

Ví dụ implementation hợp lệ:

~~~java
package com.example.impl;

import com.example.spi.Codec;

public final class GzipCodec implements Codec {
    public GzipCodec() {
        // Khởi tạo trạng thái cần thiết của provider.
    }

    @Override
    public String name() {
        return "gzip";
    }

    @Override
    public byte[] encode(byte[] input) {
        // Phần minh họa: triển khai thuật toán nén tại đây.
        return input;
    }
}
~~~

Nếu file cấu hình ghi **com.example.impl.GzipCodec** nhưng lớp thực tế nằm trong package khác, ServiceLoader không thể nạp provider. Nếu lớp được tìm thấy nhưng không triển khai đúng interface Codec, ServiceLoader cũng báo lỗi.

Một lỗi khó nhận ra là ứng dụng đóng gói hai bản service API trong các class loader khác nhau. Hai lớp có cùng tên đầy đủ vẫn có thể là hai kiểu khác nhau nếu được định nghĩa bởi hai class loader khác nhau. Provider có thể triển khai bản Codec mà nó nhìn thấy, trong khi ứng dụng yêu cầu một bản Codec khác; khi đó phép kiểm tra kiểu không thành công. Hãy bảo đảm service API được chia sẻ nhất quán giữa ứng dụng và plugin.

## 5. Các nguyên nhân thường gặp trên module path

Với JPMS, module khai báo quan hệ service bằng hai directive: **uses** ở phía ứng dụng tiêu thụ service và **provides ... with ...** ở phía module cung cấp provider.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Codec;
}
~~~

Ví dụ module provider:

~~~java
module com.example.codec.gzip {
    requires com.example.spi;
    provides com.example.spi.Codec
        with com.example.codec.gzip.GzipCodec;
}
~~~

Trong ví dụ này:
- Module ứng dụng cần đọc được module xuất bản service API và khai báo **uses** cho service mà nó nạp bằng ServiceLoader.
- Module provider cần đọc được module chứa service API và khai báo provider trong **provides**.
- Module provider phải được đưa vào cấu hình triển khai/module path phù hợp để runtime có thể tìm thấy nó.

Nếu ứng dụng nằm trong named module nhưng thiếu directive **uses**, lời gọi ServiceLoader có thể ném ServiceConfigurationError ngay khi tạo loader. Đây là trường hợp lỗi có thể xuất hiện sớm hơn lỗi do constructor của provider.

### Provider constructor và provider method

Provider trong named module có hai cách được ServiceLoader khởi tạo.

**Cách 1: provider class triển khai service và có public constructor không tham số.**

~~~java
package com.example.codec.gzip;

import com.example.spi.Codec;

public final class GzipCodec implements Codec {
    public GzipCodec() {}

    @Override
    public String name() {
        return "gzip";
    }

    @Override
    public byte[] encode(byte[] input) {
        return input;
    }
}
~~~

Khai báo module:

~~~java
provides com.example.spi.Codec
    with com.example.codec.gzip.GzipCodec;
~~~

**Cách 2: provider class có public static provider() method.**

~~~java
package com.example.codec.gzip;

import com.example.spi.Codec;

public final class GzipCodecProvider {
    public static Codec provider() {
        return new GzipCodec();
    }
}
~~~

Khai báo module:

~~~java
provides com.example.spi.Codec
    with com.example.codec.gzip.GzipCodecProvider;
~~~

Với provider method, lớp provider không cần tự triển khai Codec; phương thức **provider()** phải public, static, không có tham số và trả về một kiểu có thể gán cho Codec. ServiceLoader gọi phương thức đó để lấy instance. Nếu phương thức trả về null hoặc ném exception, ServiceConfigurationError có thể được phát sinh.

Các lỗi module thường gặp gồm: provider class không nạp được; lớp provider không triển khai service và cũng không có provider method hợp lệ; provider method trả về kiểu không tương thích; có nhiều public static method không tham số cùng tên provider; hoặc constructor/provider method ném exception.

Lưu ý: provider được đóng gói dưới dạng automatic module trên module path phải có provider constructor; cách đăng ký bằng provider method không được hỗ trợ cho automatic module.

## 6. Vì sao lỗi chỉ xuất hiện khi duyệt iterator hoặc stream?

ServiceLoader cố ý trì hoãn công việc để không phải nạp và khởi tạo mọi provider khi ứng dụng vừa gọi **load()**.

Với iterator, cả **hasNext()** và **next()** đều có thể ném ServiceConfigurationError. Vòng lặp enhanced-for cũng gọi các phương thức này ở bên dưới, vì vậy lỗi thường xuất hiện ngay tại dòng vòng lặp.

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// Dòng này tạo loader, chưa có nghĩa mọi provider đã được khởi tạo.
Iterator<Codec> iterator = loader.iterator();

while (iterator.hasNext()) {
    Codec codec = iterator.next();
    System.out.println(codec.name());
}
~~~

Với stream, các thao tác trung gian thường vẫn lazy. Lỗi được ném khi một thao tác xử lý khiến ServiceLoader phải tìm hoặc nạp provider. Trong ví dụ sau, **Provider.get()** tạo instance:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

loader.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(codec -> System.out.println(codec.name()));
~~~

Stream cho phép xem kiểu provider qua **Provider.type()** trước khi tạo instance. Điều này hữu ích khi ứng dụng cần lọc provider theo annotation hoặc metadata. Tuy nhiên, stream không loại bỏ lỗi cấu hình: thao tác tìm/nạp provider hoặc gọi **get()** vẫn có thể ném ServiceConfigurationError.

Nếu iterator đã ném lỗi, các lần gọi tiếp theo sẽ cố gắng tìm provider kế tiếp ở mức best-effort; việc phục hồi không được bảo đảm. Không nên giả định rằng bỏ qua một lỗi là có thể tiếp tục an toàn với mọi provider còn lại.

## 7. Cách xử lý lỗi trong ứng dụng

Với ứng dụng cần tất cả provider để hoạt động, cách an toàn thường là ghi log đầy đủ rồi dừng khởi tạo thành phần phụ thuộc vào SPI:

~~~java
public static List<Codec> loadCodecs() {
    List<Codec> result = new ArrayList<>();

    try {
        for (Codec codec : ServiceLoader.load(Codec.class)) {
            result.add(codec);
        }
    } catch (ServiceConfigurationError error) {
        // Giữ nguyên stack trace và cause để tìm provider bị lỗi.
        error.printStackTrace();
        throw new IllegalStateException(
            "Codec SPI không thể khởi tạo đầy đủ", error
        );
    }

    return result;
}
~~~

Với ứng dụng có plugin tùy chọn, hãy xác định rõ chính sách khi một provider lỗi: vô hiệu hóa plugin đó, hiển thị trạng thái lỗi cho người vận hành, hoặc dừng ứng dụng nếu plugin là bắt buộc. Không nên âm thầm coi provider lỗi như thể không tồn tại, vì việc đó có thể làm ứng dụng chạy với tập chức năng thiếu mà không ai nhận ra.

Nếu cần chẩn đoán lỗi khởi tạo, hãy log provider đang được xử lý, message, stack trace và cause. Nếu dùng **ServiceLoader.stream()**, có thể kiểm tra **Provider.type()** trước khi gọi **Provider.get()**; nhớ rằng cả quá trình tìm provider và việc tạo instance đều có thể phát sinh lỗi.

## 8. Quy trình chẩn đoán

Khi gặp ServiceConfigurationError, hãy đi theo thứ tự sau:

1. **Đọc message và stack trace.** Xác định service nào đang được nạp, provider nào được nhắc tới, và lỗi xảy ra ở bước tìm lớp hay khởi tạo instance.
2. **Kiểm tra cause.** Nếu cause là exception do constructor/provider method ném ra, sửa lỗi khởi tạo bên trong provider trước.
3. **Xác định cách triển khai.** Ứng dụng đang chạy provider từ classpath, automatic module hay named module? Mỗi cách có quy tắc đăng ký và khởi tạo khác nhau.
4. **Kiểm tra cấu hình classpath.** Mở JAR và xác nhận có đúng file META-INF/services/<tên đầy đủ của service>; kiểm tra từng dòng provider và bảo đảm các lớp cùng dependency có mặt lúc chạy.
5. **Kiểm tra module-info.java.** Ứng dụng phải có uses; module provider phải có provides ... with ...; các module phải đọc được service API.
6. **Kiểm tra constructor/provider method.** Với constructor, xác nhận lớp provider public, không phải inner class, triển khai đúng service và có public constructor không tham số. Với provider method, xác nhận chỉ có một phương thức public static tên provider, không có tham số và trả về kiểu tương thích.
7. **Kiểm tra class loader.** ServiceLoader.load(Service.class) sử dụng context class loader của thread hiện tại. Trong ứng dụng plugin, application server hoặc môi trường test, hãy xác nhận loader đó nhìn thấy đúng service API và provider.
8. **Thử khởi tạo provider độc lập.** Nếu đã xác định được lớp provider, chạy constructor hoặc provider method trong một bài kiểm tra nhỏ để tách lỗi khởi tạo khỏi lỗi tìm kiếm SPI.

Một số dấu hiệu và hướng kiểm tra:

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy provider class | Sai tên lớp, thiếu JAR hoặc sai runtime classpath/module path | Kiểm tra tên đầy đủ, artifact triển khai và dependency |
| Provider không phải subtype của service | Khai báo nhầm lớp hoặc hai bản service API do class loader khác nhau định nghĩa | Kiểm tra implements/extends và nguồn nạp service API |
| Thiếu provider constructor | Không có public constructor không tham số | Thêm constructor phù hợp hoặc dùng provider method trong named module |
| Module không khai báo uses | Consumer module gọi ServiceLoader nhưng thiếu directive | Thêm uses cho đúng service |
| Provider method lỗi | Sai kiểu trả về, trả null hoặc ném exception | Sửa phương thức provider() và phần khởi tạo |
| Lỗi xuất hiện ở iterator.hasNext()/next() | Provider discovery diễn ra lazy | Đọc stack trace tại điểm duyệt; kiểm tra file cấu hình và lớp provider |
| Chạy trong IDE nhưng lỗi khi đóng gói | Tài nguyên SPI hoặc JAR không được đưa vào artifact runtime | Kiểm tra nội dung JAR cuối cùng và runtime classpath/module path |

## 9. Class loader và một số lưu ý quan trọng

Lời gọi:

~~~java
ServiceLoader.load(Codec.class)
~~~

tương đương với việc dùng context class loader của thread hiện tại:

~~~java
ServiceLoader.load(
    Codec.class,
    Thread.currentThread().getContextClassLoader()
);
~~~

Nếu môi trường triển khai có nhiều class loader, loader mặc định có thể không nhìn thấy provider mà ứng dụng mong đợi. Có thể truyền loader tường minh:

~~~java
ClassLoader providerLoader = Thread.currentThread().getContextClassLoader();
ServiceLoader<Codec> loader =
    ServiceLoader.load(Codec.class, providerLoader);
~~~

Hãy chọn class loader thực sự có thể nhìn thấy cả service API và provider. Không mặc định rằng **Codec.class.getClassLoader()** luôn đúng: provider có thể nằm trong child class loader, còn service API phải được chia sẻ từ loader cha.

**ServiceLoader.loadInstalled(...)** sử dụng platform class loader. Nó dành cho provider đã cài đặt trong runtime và sẽ bỏ qua provider chỉ có trên application classpath/module path; vì vậy không dùng nó như cách thay thế chung cho **load(...)**.

ServiceLoader có cache các provider đã nạp. **reload()** xóa cache để những lần duyệt tiếp theo tìm lại provider; nó không sửa file cấu hình sai, không bổ sung JAR thiếu và không khắc phục constructor lỗi. Mỗi instance ServiceLoader cũng không an toàn khi nhiều thread sử dụng đồng thời.

## 10. Những nhầm lẫn cần tránh

- **Nhầm không có provider với provider lỗi:** không có provider là trường hợp hợp lệ; khai báo provider sai hoặc không thể khởi tạo mới tạo lỗi.
- **Cho rằng load() đã khởi tạo xong provider:** provider được tìm và khởi tạo lazy; lỗi thường xuất hiện khi duyệt iterator hoặc xử lý stream.
- **Chỉ bắt Exception:** ServiceConfigurationError kế thừa Error, nên catch Exception không bắt được nó.
- **Bắt mọi Error để bỏ qua:** điều này có thể che giấu lỗi triển khai nghiêm trọng. Chỉ bắt ServiceConfigurationError tại nơi có chính sách phục hồi rõ ràng.
- **Chỉ kiểm tra mã nguồn:** file META-INF/services, module-info.java và nội dung JAR ở runtime đều quan trọng.
- **Dùng reload() để sửa lỗi cấu hình:** reload chỉ xóa cache, không sửa nguyên nhân gốc.
- **Quên class loader:** cùng tên service không đồng nghĩa cùng một Class nếu hai loader định nghĩa hai bản khác nhau.

## 11. Tự kiểm tra

**1. ServiceLoader.load(Codec.class) chạy thành công nhưng vòng lặp for-each ném ServiceConfigurationError. Vì sao?**

Vì việc tìm và khởi tạo provider diễn ra lazy. Lỗi có thể chỉ xuất hiện khi iterator gọi hasNext() hoặc next() trong lúc duyệt.

**2. Không có file META-INF/services cho một service có nhất thiết là lỗi không?**

Không. Nếu không tìm thấy provider nào, iterator có thể rỗng và findFirst() trả về Optional.empty(). Lỗi xảy ra khi có cấu hình/provider nhưng không thể đọc, nạp hoặc khởi tạo hợp lệ.

**3. Vì sao catch (Exception e) không bắt được ServiceConfigurationError?**

Vì ServiceConfigurationError kế thừa java.lang.Error, không kế thừa Exception. Nếu cần xử lý lỗi SPI, hãy catch ServiceConfigurationError cụ thể.

**4. Ứng dụng chạy trong named module gọi ServiceLoader nhưng thiếu uses. Cần sửa ở đâu?**

Thêm directive uses cho service vào module-info.java của module tiêu thụ. Đồng thời bảo đảm module đó đọc được module xuất bản service API.

## 12. Ghi nhớ

ServiceConfigurationError báo hiệu ServiceLoader không thể hoàn thành việc tìm, nạp hoặc khởi tạo một provider. Hãy xác định provider và bước phát sinh lỗi trước, sau đó kiểm tra cấu hình classpath hoặc module path, kiểu service, constructor/provider method và class loader. Không có provider là một kết quả hợp lệ; provider được khai báo nhưng bị lỗi là một vấn đề cần xử lý rõ ràng.

## Tài liệu tham khảo

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceConfigurationError — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceConfigurationError.html)
