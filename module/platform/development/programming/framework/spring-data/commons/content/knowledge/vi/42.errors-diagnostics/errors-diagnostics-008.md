# Constructor, accessor, nullability hoặc converter không khớp dữ liệu

## 1. Truy vấn thành công chưa có nghĩa đối tượng được tạo thành công

Trong chương **Lỗi và chẩn đoán** của **SPRING_DATA_COMMONS**, cần phân biệt lỗi tìm dữ liệu với lỗi chuyển dữ liệu thành đối tượng ứng dụng.

Store có thể đã trả về một bản ghi hợp lệ về mặt lưu trữ, nhưng ứng dụng vẫn thất bại vì:

- Không chọn được constructor hoặc factory phù hợp.
- Không gắn được dữ liệu với tham số khởi tạo.
- Không ghi hoặc đọc được property theo chiến lược access đang dùng.
- Null đi vào một vị trí không chấp nhận null.
- Không có converter cho kiểu dữ liệu thực tế.
- Converter chạy nhưng từ chối giá trị.
- Projection hoặc getter không phù hợp với kết quả query.

Repository và CRUD là abstraction chung; cơ chế materialization, annotation mapping và kiểu dữ liệu gốc vẫn phụ thuộc module/store.

Bài học này hướng dẫn tìm điểm không khớp giữa **dữ liệu thực tế**, **metadata mapping** và **hợp đồng domain**, thay vì sửa ngẫu nhiên constructor hoặc thêm setter cho đến khi hết exception.

## 2. Hình dung các checkpoint của quá trình đọc

~~~text
Dữ liệu gốc từ store
  → Nhận diện kiểu và tên field/cột
    → Chuyển đổi giá trị cần thiết
      → Cung cấp đối số cho constructor/factory
        → Hoàn tất các property còn lại
          → Trả entity hoặc projection
            → Getter, mapper và serializer sử dụng kết quả
~~~

Đây là các checkpoint để chẩn đoán, không phải thứ tự nội bộ bắt buộc của mọi module. Conversion, khởi tạo và property population có thể đan xen theo implementation.

Cần xác định lỗi xuất hiện tại đâu:

| Thời điểm | Nhóm nguyên nhân đáng kiểm tra |
| --- | --- |
| Khởi tạo metadata/context | Creator nhập nhằng, mapping không hợp lệ |
| Đọc một bản ghi cụ thể | Kiểu thực tế, dữ liệu cũ, null hoặc giá trị không hợp lệ |
| Sau khi entity đã được tạo | Accessor, getter tính toán, lazy reference |
| Khi đọc projection | Alias, kiểu accessor hoặc constructor DTO |
| Khi serialize response | Getter, serializer hoặc tài nguyên không còn hợp lệ |
| Khi ghi dữ liệu | Writing converter, property access hoặc kiểu store không hỗ trợ |

Không đổi converter lưu trữ chỉ vì lỗi nằm trong serializer HTTP. Cần giữ đúng ranh giới của vấn đề.

## 3. Đọc exception theo điểm thất bại

Một số nhóm exception có thể gặp:

| Nhóm lỗi | Ý nghĩa cần tìm hiểu |
| --- | --- |
| MappingInstantiationException | Không tạo được instance theo cơ chế mapping đang dùng |
| ConverterNotFoundException | Không tìm được conversion phù hợp giữa các kiểu |
| ConversionFailedException | Conversion được thử nhưng không hoàn tất |
| MappingException | Có vấn đề mapping; cần đọc nguyên nhân cụ thể |
| IllegalArgumentException | Constructor, accessor hoặc converter có thể từ chối giá trị |
| NullPointerException | Có thể do invariant, unboxing hoặc getter; không chỉ do một nguyên nhân |
| Exception của provider/driver | Có thể phát sinh trước hoặc trong materialization |

Tên và cách bọc exception khác nhau giữa các module và provider. Không yêu cầu mọi lỗi constructor phải có cùng chuỗi wrapper.

Khi đọc lỗi, tìm:

1. Kiểu domain hoặc projection đang được tạo.
2. Constructor/factory được lựa chọn.
3. Property hoặc tham số liên quan.
4. Kiểu nguồn và kiểu đích của conversion.
5. Nguyên nhân gốc mà mã domain hoặc converter ném ra.
6. Bản ghi nào có hình dạng dữ liệu gây lỗi.

Một MappingInstantiationException có thể chỉ là lớp bọc cho việc constructor từ chối displayName rỗng. Thêm constructor khác không tự sửa dữ liệu đó.

## 4. Ví dụ dữ liệu cũ không khớp mô hình mới

Giả sử một document cũ có dạng:

~~~json
{
  "_id": "customer-42",
  "display_name": "Nguyễn An",
  "birth_year": null,
  "credit_limit": "1.234,50"
}
~~~

Mô hình mới mong đợi:

~~~text
id: String
displayName: String bắt buộc
birthYear: Integer có thể null
creditLimit: value object từ chuỗi số thập phân chuẩn
~~~

Có nhiều khả năng không khớp độc lập:

| Thay đổi trong code | Điều cần kiểm tra |
| --- | --- |
| Đổi display_name thành displayName ở domain | Mapping alias còn trỏ đúng field cũ không? |
| Dùng int cho birthYear | Null được biểu diễn hoặc từ chối thế nào? |
| Đưa creditLimit thành value object | Converter có nhận đúng kiểu String không? |
| Chỉ chấp nhận chuỗi như 1234.50 | Dữ liệu 1.234,50 theo định dạng cũ được xử lý thế nào? |
| Thêm constructor có invariant mới | Bản ghi cũ có đáp ứng invariant không? |

Không sửa tất cả cùng lúc mà không giữ một trường hợp tái hiện. Nên cô lập từng bất tương thích và chọn cách xử lý theo chính sách dữ liệu.

Bản ghi mới do ứng dụng hiện tại tạo ra có thể đọc được, trong khi một bản ghi lịch sử thất bại. Đây là dấu hiệu quan trọng cho vấn đề tương thích dữ liệu, không chỉ vấn đề wiring.

## 5. Constructor: chọn đúng creator và đúng đối số

Các module mapping của Spring Data có cơ chế chọn constructor hoặc factory theo metadata được hỗ trợ. Có thể sử dụng PersistenceCreator để chỉ rõ một creator trong trường hợp phù hợp.

Ví dụ dưới đây chọn **mapping MongoDB** để minh họa cụ thể:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customer_profile")
public class CustomerProfile {

    @Id
    private final String id;

    @Field("display_name")
    private final String displayName;

    @Field("birth_year")
    private final Integer birthYear;

    @Field("credit_limit")
    private final CreditLimit creditLimit;

    @PersistenceCreator
    public CustomerProfile(
            String id,
            String displayName,
            Integer birthYear,
            CreditLimit creditLimit) {

        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "displayName là thông tin bắt buộc");
        }

        this.id = id;
        this.displayName = displayName;
        this.birthYear = birthYear;
        this.creditLimit = creditLimit;
    }

    public CustomerProfile(String displayName) {
        this(null, displayName, null, null);
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Integer getBirthYear() { return birthYear; }
    public CreditLimit getCreditLimit() { return creditLimit; }
}
~~~

CreditLimit sẽ được định nghĩa ở phần converter. Ví dụ cho phép birthYear và creditLimit chưa có giá trị, nhưng yêu cầu displayName hợp lệ.

Đoạn này tập trung vào việc đọc đối tượng có ID đã có trong dữ liệu. Nếu cần cấp ID cho một immutable entity mới, phải dùng cơ chế tái tạo/copy hoặc wither mà module hỗ trợ, không suy ra final field luôn có thể được gán lại.

### Tên tham số và tên lưu trữ khác nhau

Constructor dùng displayName, là tên property domain. Field được mapping sang display_name.

Không đổi tham số thành display_name chỉ vì document có tên đó. Cần để hạ tầng mapping nối property domain với biểu diễn lưu trữ theo metadata.

Module có thể cần thông tin tên tham số trong bytecode hoặc metadata được hỗ trợ để bind đối số. Khi build không giữ thông tin cần thiết, một constructor nhìn đúng trên mã nguồn vẫn có thể không được bind như dự kiến.

PersistenceCreator giúp chọn creator trong cơ chế hỗ trợ nó; annotation không tự sửa tên property, kiểu dữ liệu hoặc dữ liệu thiếu.

### Không thêm no-arg constructor theo phản xạ

Thêm constructor rỗng có thể:

- Làm thay đổi creator được lựa chọn.
- Đưa quá trình sang property population.
- Cho phép trạng thái tạm thời không hợp lệ.
- Che vấn đề dữ liệu thiếu mà constructor cũ đã phát hiện.

Chỉ thêm khi đó là thiết kế phù hợp với module và domain.

### JPA là trường hợp cần phân biệt

JPA entity được khởi tạo theo cơ chế của JPA provider và mapping của nó, bao gồm yêu cầu constructor thích hợp của entity. PersistenceCreator không thay thế cơ chế đó.

DTO/constructor projection của JPA cũng có hợp đồng riêng. Không lấy một ví dụ constructor mapping của MongoDB rồi mặc định áp dụng nguyên vẹn cho JPA entity.

## 6. Record và immutable object vẫn có invariant

Record có canonical constructor; các module hỗ trợ record có thể sử dụng thông tin đó khi materialize.

~~~java
public record CustomerSnapshot(
        String id,
        String displayName,
        Integer birthYear) {

    public CustomerSnapshot {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "displayName không được thiếu");
        }
    }
}
~~~

Nếu dữ liệu cũ không có displayName, canonical constructor vẫn có thể từ chối. Việc đổi class thành record không làm dữ liệu tự trở nên hợp lệ.

Với immutable object, cần kiểm tra:

- Mọi property cần thiết có được cung cấp qua creator không?
- Các tên và kiểu đối số có khớp không?
- Có property final nào bị để lại cho bước population mà cơ chế hiện tại không xử lý được không?
- Wither hoặc copy mechanism có trả instance mới đúng dữ liệu không?
- Caller có sử dụng instance được thao tác lưu trả về không?

Không cho rằng getter đầy đủ thì đối tượng chắc chắn có thể được tạo. Đọc property và khởi tạo property là hai khả năng khác nhau.

## 7. Accessor: cần biết hạ tầng dùng field hay property

Một domain có field, getter và setter không có nghĩa mọi module sẽ chọn cùng chiến lược access.

Có thể có:

~~~text
Đọc/ghi trực tiếp field.
Gọi getter/setter.
Cung cấp giá trị qua constructor.
Tạo bản sao bằng cơ chế immutable được hỗ trợ.
~~~

Điểm cần kiểm tra là chiến lược **thực sự có hiệu lực**.

### Getter không phản ánh field

Ví dụ:

~~~java
public String getDisplayName() {
    return displayName.strip();
}
~~~

Nếu displayName bị null, getter ném lỗi dù mapping đã tạo được object. Stack trace lúc này có thể dẫn qua DTO mapper hoặc serializer.

Không nên kết luận constructor hỏng chỉ vì object không serialize được.

Một getter cũng có thể trả kiểu hoặc giá trị khác với field mà metadata đang sử dụng. Với property access, việc này có thể ảnh hưởng conversion hoặc giá trị lưu.

### Setter có validation hoặc side effect

Nếu mapping dùng setter, các kiểm tra trong setter có thể được kích hoạt khi đọc dữ liệu. Một giá trị lịch sử không hợp lệ theo quy tắc mới có thể bị từ chối ở đây thay vì constructor.

Cần xác định domain muốn:

- Từ chối dữ liệu không hợp lệ.
- Chuyển đổi dữ liệu cũ qua một đường tương thích.
- Hay migration dữ liệu trước khi đọc bằng mô hình mới.

Không xóa validation chỉ để dữ liệu lỗi đi qua mà chưa xác định ngữ nghĩa.

### Kế thừa và property cùng tên

Class con có property cùng tên nhưng khác kiểu hoặc getter không tương thích có thể làm metadata khó hiểu.

Khi lỗi nói kiểu đích khác điều bạn dự kiến, hãy kiểm tra cả superclass, property bị che và accessor được chọn, không chỉ field trong class đang mở.

## 8. Nullability: thiếu field, null và giá trị mặc định là ba chuyện khác nhau

Cần phân biệt:

| Dữ liệu | Ý nghĩa có thể có |
| --- | --- |
| Không có field | Dữ liệu từ phiên bản cũ hoặc thuộc tính chưa được ghi |
| Field có giá trị null | Có thể biểu thị chưa biết hoặc chưa được cấu hình |
| Chuỗi rỗng | Có giá trị chuỗi nhưng có thể không hợp lệ |
| Số 0 | Một giá trị số cụ thể, không tự đồng nghĩa chưa biết |

Store và mapping có thể xử lý missing/null theo cách khác nhau. Nếu sự khác biệt quan trọng, cần kiểm tra sự hiện diện của field ở biểu diễn gốc.

### Primitive và wrapper

Nếu birthYear có thể chưa biết, Integer biểu đạt được null; int không biểu đạt được trạng thái đó.

Tùy cơ chế mapping, null vào primitive có thể gây lỗi hoặc dẫn đến một hành vi mặc định. Không dựa vào giả định rằng mọi trường hợp đều ném cùng exception.

Đổi null thành 0 chỉ để hết lỗi có thể tạo một năm sinh không có nghĩa nghiệp vụ. Giá trị mặc định phải có chính sách rõ, không phải mẹo kỹ thuật.

### Annotation không tự tạo mọi ràng buộc

Một annotation nullability ở Java không tự tạo constraint database. Ngược lại, một constraint store không giải thích toàn bộ khả năng null của projection hoặc dữ liệu cũ.

Bean Validation cũng chỉ có tác dụng ở những điểm mà hạ tầng validation thực sự được kích hoạt. Không mặc định mọi lần materialize đều tự chạy mọi annotation kiểm tra.

### Optional ở repository không bảo vệ mọi property

Optional<CustomerProfile> có thể biểu đạt không có kết quả. Nó không chứng minh các property bên trong CustomerProfile đều khác null.

Một truy vấn có bản ghi nhưng không materialize được vẫn là lỗi mapping, không phải Optional.empty theo nghĩa “không tìm thấy”.

Với Kotlin, nullability và giá trị mặc định của tham số có thể tham gia cơ chế mapping theo hỗ trợ của module. Cần kiểm tra metadata và hợp đồng cụ thể; không coi default parameter là cách tự động sửa mọi dữ liệu không hợp lệ.

## 9. Converter: đối chiếu kiểu nguồn thực tế trước khi sửa logic

Giả sử credit_limit cần lưu bằng chuỗi số thập phân chuẩn, ví dụ 1234.50.

Value object:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record CreditLimit(BigDecimal amount) {

    public CreditLimit {
        Objects.requireNonNull(amount, "amount");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "Hạn mức không được âm");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Chính sách ví dụ yêu cầu giá trị không âm và biểu diễn được với hai chữ số thập phân mà không làm tròn mất thông tin.

Converter đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class CreditLimitReadConverter
        implements Converter<String, CreditLimit> {

    @Override
    public CreditLimit convert(String source) {
        return new CreditLimit(new BigDecimal(source));
    }
}
~~~

Converter ghi:

~~~java
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class CreditLimitWriteConverter
        implements Converter<CreditLimit, String> {

    @Override
    public String convert(CreditLimit source) {
        return source.amount().toPlainString();
    }
}
~~~

Các converter cần được đăng ký qua cơ chế custom conversions của module. Annotation về chiều conversion không tự chứng minh cấu hình thực tế đã đăng ký chúng.

### Tách các loại lỗi

| Dữ liệu thực tế | Khả năng gây lỗi |
| --- | --- |
| String 1234.50 | Phù hợp converter minh họa |
| String 1.234,50 | Không thuộc định dạng BigDecimal(String) mong đợi |
| String không phải số | Logic conversion từ chối |
| Số native của store | Có thể không chọn converter có source type String |
| Document lồng | Cần mapping/conversion khác hoặc migration |
| Null | Cần xem hạ tầng bỏ qua hay xử lý theo chính sách nào |

Nếu converter không được chọn vì source type khác, sửa thân convert(String) sẽ không giải quyết được đường gọi đó.

Nếu converter được gọi và ném NumberFormatException, vấn đề khác với ConverterNotFoundException. Cần đọc cả source type và giá trị theo đúng định dạng, không chỉ tên field.

### Đừng chuẩn hóa số theo cách mơ hồ

Tự xóa dấu chấm và dấu phẩy có thể làm thay đổi ý nghĩa. Một chuỗi có thể mang quy ước locale khác hoặc đã là số thập phân chuẩn.

Nếu hỗ trợ dữ liệu cũ, hãy định nghĩa định dạng được chấp nhận và quy tắc phân biệt rõ. Nếu không thể xác định ý nghĩa, cần xử lý dữ liệu đó theo chính sách thay vì đoán.

Không dùng double làm bước trung gian mặc định cho dữ liệu cần độ chính xác thập phân.

## 10. Đọc đúng không đủ: cần kiểm tra cả biểu diễn ghi

Một converter đọc có thể nhận được dữ liệu mới, nhưng writing converter lại ghi ra hình dạng khác.

Ví dụ:

~~~text
Đọc mong đợi: String.
Ghi thực tế: object/document chứa amount.
~~~

Round trip với cùng một mapping có thể che một số khác biệt nếu cả hai chiều đều dùng biểu diễn không đúng hợp đồng đã thỏa thuận.

Nên kiểm tra:

1. Giá trị domain sau khi đọc.
2. Biểu diễn raw sau khi ghi.
3. Khả năng đọc dữ liệu từ phiên bản trước.
4. Độ chính xác và ngữ nghĩa sau round trip.

Một converter quá rộng có thể ảnh hưởng nhiều property khác ngoài nơi đang sửa. Nên dùng kiểu domain cụ thể và chiều conversion rõ khi phù hợp.

Với thời gian, cần thêm chính sách timezone và precision. Chuỗi thời gian cũ không có timezone không tự chỉ ra một Instant duy nhất; dùng timezone mặc định của máy có thể tạo kết quả khác giữa môi trường.

## 11. Projection có thể có lỗi riêng dù entity mapping đúng

Giả sử entity đọc được, nhưng projection khai báo:

~~~java
public interface CustomerView {
    String getDisplayName();
    int getBirthYear();
}
~~~

Nếu dữ liệu birthYear là null, accessor int không biểu đạt được giá trị đó. Lỗi có thể chỉ xuất hiện khi gọi getter.

Với query tường minh hoặc native query, alias cũng có thể không khớp accessor projection. Ví dụ result mang tên display_name nhưng cơ chế projection đang kỳ vọng displayName theo hợp đồng của dạng query đó.

Cần kiểm tra:

- Tên alias.
- Kiểu trả về của accessor.
- Nullability.
- Kiểu dữ liệu thực tế từ driver/provider.
- Constructor và thứ tự/metadata của DTO projection nếu áp dụng.

Quy tắc alias của một loại query không phải quy tắc chung cho mọi store. Không sửa entity constructor nếu lỗi chỉ nằm trong một projection không dùng constructor đó.

## 12. Quy trình chẩn đoán từng bước

### Bước 1: Cố định một trường hợp tái hiện

Xác định ID hoặc điều kiện chọn đúng bản ghi thất bại. Giữ lại hình dạng dữ liệu tối thiểu có liên quan và thao tác repository đang chạy.

Nếu chỉ một số bản ghi lỗi, so sánh một bản ghi đọc được và một bản ghi không đọc được.

### Bước 2: Xem biểu diễn gốc

Đối chiếu tên field/cột, sự hiện diện và kiểu dữ liệu thực tế. Không chỉ nhìn JSON đã được DTO mapper chuyển đổi.

Dữ liệu nhìn giống số trên màn hình có thể là String, kiểu số native hoặc document chứa số. Các trường hợp này chọn conversion khác nhau.

### Bước 3: Xác định creator và access strategy

Tìm constructor/factory được chọn, tên tham số, kiểu đối số và chiến lược population của module.

Phân biệt lỗi không chọn được creator với lỗi creator đã được gọi rồi từ chối dữ liệu.

### Bước 4: Kiểm tra nullability theo từng vị trí

Không chỉ kiểm tra annotation. Đối chiếu primitive/wrapper, invariant constructor, getter và schema dữ liệu cũ.

### Bước 5: Kiểm tra conversion

Xác định source type, target type, converter đăng ký và chiều conversion. Kiểm tra converter có thực sự được gọi trong đường đọc đang xét không.

### Bước 6: Xác định lớp gây lỗi cuối

Nếu entity tạo thành công, kiểm tra mapper, projection và serializer. Không quy mọi exception sau query cho persistence constructor.

### Bước 7: Chọn cách sửa đúng hợp đồng

Có thể sửa code, mapping hoặc dữ liệu. Lựa chọn cần giải thích vì sao dữ liệu cũ và dữ liệu mới sẽ được đọc/ghi nhất quán.

### Bước 8: Kiểm chứng với cả dữ liệu đại diện và dữ liệu biên

Không chỉ thử lại bản ghi đã sửa. Cần có missing, null, giá trị hợp lệ, giá trị không hợp lệ và representation của phiên bản cũ nếu được hỗ trợ.

## 13. Chọn giữa sửa mapping, tương thích đọc và migration

| Nguyên nhân | Hướng xử lý phù hợp |
| --- | --- |
| Alias sai | Sửa metadata mapping theo schema/field đã thỏa thuận |
| Creator nhập nhằng | Chọn creator rõ theo cơ chế module |
| Thiếu metadata tham số | Sửa cách cung cấp metadata cần thiết |
| Null là trạng thái hợp lệ | Dùng mô hình biểu đạt được trạng thái đó |
| Null vi phạm nghiệp vụ | Sửa dữ liệu hoặc từ chối với chẩn đoán rõ |
| Representation cũ có quy tắc xác định | Converter tương thích hoặc migration có kiểm soát |
| Representation không xác định được ý nghĩa | Phân loại và xử lý dữ liệu theo chính sách |
| Projection sai kiểu/alias | Sửa hợp đồng projection |
| Immutable object thiếu đường cập nhật | Dùng cơ chế copy/wither/constructor phù hợp |

Một reader chấp nhận cả định dạng cũ và mới có thể hỗ trợ giai đoạn chuyển đổi. Writer nên có một định dạng chuẩn được xác định rõ, nếu đó là chính sách đã chọn.

Cần đánh giá tương thích khi nhiều phiên bản ứng dụng cùng hoạt động: bản cũ có đọc được dữ liệu do writer mới tạo không? Không chỉ kiểm tra chiều “code mới đọc dữ liệu cũ”.

Migration cũng cần kiểm tra tính đầy đủ và khả năng chạy lại theo yêu cầu. Không âm thầm coi mọi giá trị không parse được là 0 hoặc null.

## 14. Kiểm thử từ logic đơn vị đến repository thật

### Converter unit test

~~~java
@Test
void readsCanonicalDecimal() {
    CreditLimitReadConverter reader = new CreditLimitReadConverter();

    CreditLimit limit = reader.convert("1234.50");

    assertThat(limit.amount())
            .isEqualByComparingTo("1234.50");
}

@Test
void rejectsUnsupportedLegacyNumberFormat() {
    CreditLimitReadConverter reader = new CreditLimitReadConverter();

    assertThatThrownBy(() -> reader.convert("1.234,50"))
            .isInstanceOf(NumberFormatException.class);
}
~~~

Đây là minh họa với JUnit Jupiter và AssertJ. Test thứ hai chứng minh chính sách hiện tại từ chối định dạng đó; nếu sản phẩm phải hỗ trợ nó, cần thay chính sách và test tương ứng.

### Mapping test từ dữ liệu raw

Với bean Mongo converter đã được cấu hình đúng:

~~~java
org.bson.Document raw = new org.bson.Document("_id", "customer-42")
        .append("display_name", "Nguyễn An")
        .append("birth_year", null)
        .append("credit_limit", "1234.50");

CustomerProfile profile =
        mongoConverter.read(CustomerProfile.class, raw);

assertThat(profile.getDisplayName()).isEqualTo("Nguyễn An");
assertThat(profile.getBirthYear()).isNull();
assertThat(profile.getCreditLimit().amount())
        .isEqualByComparingTo("1234.50");
~~~

Test này đi qua cấu hình converter/mapping được cung cấp, nhưng chưa chứng minh repository, driver và store thật đang dùng cùng cấu hình.

Không tạo một converter độc lập với cấu hình khác rồi coi kết quả là bằng chứng cho bean production.

### Integration test với dữ liệu được chèn ở biểu diễn lưu trữ

Một phép kiểm chứng mạnh hơn cho dữ liệu lịch sử là:

~~~text
Chèn raw document/row theo fixture.
Đọc qua repository thật.
Kiểm tra đối tượng và các invariant.
Ghi lại nếu đó là một phần use case.
Đọc raw representation để kiểm tra writer.
~~~

Chỉ tạo domain object mới rồi save có thể bỏ qua chính hình dạng dữ liệu cũ đang gây lỗi. Fixture raw giúp tránh việc writer hiện tại tự chuẩn hóa mọi giá trị trước khi test đọc.

Với JPA, cần kiểm soát persistence context khi kiểm tra đường đọc thật. Với MongoDB hoặc module khác, dùng cơ chế phù hợp của module, không sao chép flush/clear của JPA một cách máy móc.

## 15. Ma trận dữ liệu cần kiểm tra

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Đủ field và kiểu chuẩn | Đường đọc/ghi thông thường đúng |
| Thiếu field tùy chọn | Mô hình biểu đạt được trạng thái chưa có |
| Field tùy chọn bằng null | Null không bị biến thành giá trị nghiệp vụ sai |
| Thiếu field bắt buộc | Thất bại rõ hoặc được migration theo chính sách |
| Giá trị rỗng | Được phân biệt với missing/null |
| Source type khác phiên bản mới | Converter tương thích hoặc từ chối rõ |
| Giá trị vượt precision/range | Không mất thông tin âm thầm |
| Constructor có invariant | Invariant được giữ khi materialize |
| Getter có xử lý | Không lỗi muộn ngoài dự kiến |
| Projection có field null | Accessor và kiểu trả về phù hợp |
| Enum có giá trị lịch sử | Chính sách tương thích được kiểm chứng |
| Timestamp khác biểu diễn | Timezone/precision được xử lý có chủ đích |

Một test chỉ assert object khác null thường không đủ. Cần kiểm tra các field có ý nghĩa và biểu diễn có khả năng bị sai.

Mock repository trả một object đã được new thành công không xác minh constructor binding, mapping hoặc conversion từ dữ liệu gốc.

## 16. Những cách xử lý dễ che mất nguyên nhân

- Thêm constructor rỗng mà chưa biết creator hiện tại vì sao thất bại.
- Thêm setter cho mọi final field mà chưa xác định mô hình immutable.
- Đổi mọi primitive thành wrapper nhưng không kiểm tra nghiệp vụ.
- Gán 0, chuỗi rỗng hoặc ngày hiện tại cho dữ liệu thiếu.
- Bắt mọi lỗi mapping rồi trả Optional.empty.
- Bỏ qua converter bị lỗi và dùng giá trị mặc định.
- Xóa validation constructor để chấp nhận dữ liệu không có nghĩa.
- Chỉ kiểm tra bản ghi mới, bỏ qua dữ liệu lịch sử.
- Sửa serializer trong khi lỗi xảy ra trước khi entity được tạo.
- Cho rằng annotation converter tự bảo đảm mọi đường đọc/ghi đã đăng ký nó.

Những thay đổi này có thể làm exception biến mất nhưng để lại dữ liệu sai hoặc làm mất thông tin. Mục tiêu là khôi phục hợp đồng đúng, không chỉ làm đường chạy tiếp tục.

## 17. Bài tập áp dụng

1. Dựng một raw record có birthYear null và so sánh mô hình int với Integer.
2. Tạo constructor có invariant displayName và xác định lỗi khi field bị thiếu.
3. Mapping display_name sang displayName rồi kiểm chứng bind constructor.
4. Đăng ký converter CreditLimit và kiểm tra source type String cùng một source type khác.
5. So sánh định dạng 1234.50 với định dạng lịch sử 1.234,50 và chọn chính sách xử lý.
6. Đọc entity thật, sau đó gọi projection/getter để phân biệt lỗi materialization với lỗi sử dụng kết quả.
7. Kiểm tra cả raw representation sau ghi lẫn domain sau đọc.
8. Viết một kết luận chẩn đoán nêu rõ bản ghi, field, kiểu dữ liệu, creator/converter và hướng sửa.

Chẩn đoán mapping hiệu quả cần nối được dữ liệu gốc với hợp đồng khởi tạo và sử dụng đối tượng. Constructor, accessor, nullability và converter phải cùng thống nhất với dữ liệu thực tế cùng khả năng của module store đang dùng.
