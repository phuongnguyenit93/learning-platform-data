# Phân biệt thay thế giá trị và hợp nhất cấu trúc bằng JsonMerge

## 1. Hai cách cập nhật JSON khác nhau

Khi một ứng dụng nhận JSON để cập nhật một object Java đã tồn tại, có hai cách xử lý phổ biến:

- **Thay thế (replace):** giá trị property mới thay cho giá trị cũ. Với một object lồng nhau, Jackson có thể tạo object mới từ JSON rồi gán vào property, khiến các field cũ không được gửi bị mất.
- **Hợp nhất (merge):** dữ liệu mới được áp dụng lên cấu trúc hiện tại. Những phần không được đề cập có thể tiếp tục giữ giá trị cũ, trong khi phần được gửi sẽ được cập nhật.

Jackson cung cấp annotation JsonMerge để yêu cầu hợp nhất một property trong các thao tác cập nhật object có sẵn. Annotation này đặc biệt hữu ích với POJO lồng nhau, Map và Collection.

Ví dụ, object hiện tại:

~~~json
{
  "id": "U-10",
  "profile": {
    "city": "Da Nang",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "preferences": {
    "theme": "light",
    "language": "vi"
  }
}
~~~

JSON cập nhật chỉ gửi:

~~~json
{
  "profile": {
    "city": "Hue"
  },
  "preferences": {
    "theme": "dark"
  }
}
~~~

Nếu thay thế toàn bộ các property lồng nhau, profile có thể mất timezone và preferences có thể mất language. Nếu hợp nhất, city đổi thành Hue, theme đổi thành dark, còn timezone và language được giữ lại.

## 2. JsonMerge hoạt động trong thao tác cập nhật

JsonMerge thuộc package com.fasterxml.jackson.annotation. Nó đánh dấu property cần được hợp nhất với giá trị đang tồn tại thay vì thay thế giá trị đó khi Jackson thực hiện update.

Các API thường dùng để cập nhật object có sẵn:

- ObjectReader.readerForUpdating(existing).readValue(json)
- ObjectMapper.updateValue(existing, overrides)

Ví dụ với readerForUpdating:

~~~java
ObjectMapper mapper = new ObjectMapper();

Account account = loadExistingAccount();
String updateJson = """
        {
          "displayName": "Lan Nguyen"
        }
        """;

mapper.readerForUpdating(account).readValue(updateJson);
~~~

Jackson áp dụng các property có trong JSON lên instance account. Property không xuất hiện thường không được cập nhật. JsonMerge thay đổi cách một property có mặt được áp dụng khi giá trị hiện tại của nó là một cấu trúc có thể hợp nhất.

Điểm cần nhớ: JsonMerge không phải lệnh tự động hợp nhất mọi lần gọi readValue() vào một object mới. Khi tạo object mới, không có giá trị cũ để hợp nhất. Annotation phát huy tác dụng trong update operation có một instance hiện hữu.

## 3. Ví dụ mô hình Java

Giả sử tài khoản có một profile lồng nhau, một map tùy chọn và một danh sách tag:

~~~java
public class Profile {
    private String city;
    private String timezone;

    public Profile() {
    }

    public Profile(String city, String timezone) {
        this.city = city;
        this.timezone = timezone;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getTimezone() {
        return timezone;
    }

    public void setTimezone(String timezone) {
        this.timezone = timezone;
    }
}
~~~

Đánh dấu các property cần merge:

~~~java
import com.fasterxml.jackson.annotation.JsonMerge;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Account {
    private String id;
    private String displayName;

    @JsonMerge
    private Profile profile;

    @JsonMerge
    private Map<String, String> preferences = new LinkedHashMap<>();

    @JsonMerge
    private List<String> tags = new ArrayList<>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Profile getProfile() {
        return profile;
    }

    public void setProfile(Profile profile) {
        this.profile = profile;
    }

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void setPreferences(Map<String, String> preferences) {
        this.preferences = preferences;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

JsonMerge được đặt trên property cần cập nhật theo kiểu merge. Các property khác như id và displayName vẫn dùng hành vi cập nhật thông thường.

## 4. Cập nhật POJO lồng nhau: giữ field không được gửi

Tạo object hiện tại:

~~~java
Account account = new Account();
account.setId("U-10");
account.setDisplayName("Lan");
account.setProfile(
        new Profile("Da Nang", "Asia/Ho_Chi_Minh")
);
~~~

Thực hiện update:

~~~java
String json = """
        {
          "profile": {
            "city": "Hue"
          }
        }
        """;

ObjectMapper mapper = new ObjectMapper();
mapper.readerForUpdating(account).readValue(json);
~~~

Vì property profile có JsonMerge, Jackson cập nhật object Profile hiện có. Field city được thay bằng Hue; field timezone không có trong JSON nên giữ nguyên.

Kết quả:

~~~java
System.out.println(account.getProfile().getCity()); // Hue
System.out.println(account.getProfile().getTimezone()); // Asia/Ho_Chi_Minh
~~~

Nếu bỏ JsonMerge khỏi profile, Jackson có thể deserialize một Profile mới từ object JSON được gửi rồi thay thế property hiện tại. Object mới chỉ có city; timezone không được gửi nên sẽ nhận giá trị mặc định của kiểu (ở đây là null).

| Cách cập nhật profile | city | timezone |
|---|---|---|
| Không dùng JsonMerge | Hue | null |
| Dùng JsonMerge | Hue | Asia/Ho_Chi_Minh |

Đây là khác biệt cốt lõi giữa replace và merge đối với một POJO lồng nhau.

## 5. Hợp nhất Map theo key

Với Map, merge xử lý các entry theo key:

- Key chỉ có trong Map cũ tiếp tục tồn tại.
- Key xuất hiện trong JSON được thêm vào nếu chưa có.
- Key đã tồn tại được cập nhật bằng giá trị mới.

Giả sử Map ban đầu:

~~~java
account.getPreferences().put("theme", "light");
account.getPreferences().put("language", "vi");
~~~

JSON cập nhật:

~~~json
{
  "preferences": {
    "theme": "dark",
    "notifications": "enabled"
  }
}
~~~

Sau update với JsonMerge:

~~~json
{
  "theme": "dark",
  "language": "vi",
  "notifications": "enabled"
}
~~~

Ví dụ:

~~~java
String json = """
        {
          "preferences": {
            "theme": "dark",
            "notifications": "enabled"
          }
        }
        """;

mapper.readerForUpdating(account).readValue(json);

System.out.println(account.getPreferences());
~~~

Không có JsonMerge, property Map thường bị thay thế bằng Map được tạo từ payload mới; key language sẽ mất. Khi có JsonMerge, các key cũ không được nhắc đến được giữ lại.

Với Map có value là object hoặc Map lồng nhau, cách cập nhật sâu bên trong value còn phụ thuộc deserializer của value và metadata merge tại property tương ứng. Không nên giả định một annotation trên Map luôn tạo ra phép deep merge đệ quy cho mọi cấu trúc lồng nhau. Hãy đặt chính sách merge ở đúng ranh giới property và kiểm thử cấu trúc thực tế.

## 6. Hợp nhất Collection: phần tử mới được thêm vào

Với Collection được hỗ trợ, merge thường áp dụng các phần tử đầu vào vào collection hiện tại thay vì thay collection bằng một instance mới. Với List, hành vi thông thường là nối thêm phần tử từ JSON vào cuối danh sách.

Ví dụ danh sách ban đầu:

~~~java
account.getTags().add("beta");
account.getTags().add("newsletter");
~~~

JSON cập nhật:

~~~json
{
  "tags": ["premium"]
}
~~~

Sau merge, danh sách có dạng:

~~~json
["beta", "newsletter", "premium"]
~~~

Merge collection không tự hiểu phần tử nào là cùng một thực thể nghiệp vụ. Nếu gửi lại beta, phần tử đó có thể được thêm lần nữa. JsonMerge không tự loại bỏ phần tử trùng, không cập nhật một phần tử theo ID và không suy ra lệnh xóa từ việc phần tử không xuất hiện.

Nếu cần thay toàn bộ danh sách, không dùng merge cho property đó hoặc cung cấp thao tác thay thế riêng. Nếu cần cập nhật theo ID, cần viết logic domain hoặc custom deserializer phù hợp với mô hình dữ liệu.

## 7. Scalar và array không có cùng ngữ nghĩa merge

Merge có ý nghĩa rõ nhất với cấu trúc có thể cập nhật từng phần. Với giá trị scalar như String, Integer, Boolean hoặc enum, không có các thành phần con để hợp nhất; giá trị mới thường thay thế giá trị cũ.

Ví dụ:

~~~java
account.setDisplayName("Lan");

mapper.readerForUpdating(account).readValue("""
        {"displayName":"Lan Nguyen"}
        """);

System.out.println(account.getDisplayName()); // Lan Nguyen
~~~

JsonMerge không biến một String thành cấu trúc ghép ký tự. Nếu đặt annotation trên scalar, nó không tạo ra một phép merge có ý nghĩa tương đương POJO, Map hoặc Collection; hãy dùng cập nhật giá trị thông thường.

Array Java có kích thước cố định và không thể thêm phần tử trực tiếp. Jackson không hỗ trợ merge array theo cách nối thêm như Collection; trong update, array được xử lý theo hướng thay thế giá trị. Nếu cần thêm/bớt phần tử, dùng Collection như List hoặc tự viết quy tắc cập nhật.

| Loại property | Hành vi merge thường gặp |
|---|---|
| POJO lồng nhau | Cập nhật object hiện có theo các property được gửi |
| Map | Hợp nhất entry theo key |
| Collection/List | Thêm các phần tử đầu vào vào collection hiện có |
| Array Java | Không hỗ trợ merge như Collection; dùng giá trị mới để thay thế |
| Scalar | Không có cấu trúc con để merge; giá trị mới thay thế |

## 8. Chạy update với readerForUpdating

Một ví dụ đầy đủ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public class MergeExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        Account account = new Account();
        account.setId("U-10");
        account.setDisplayName("Lan");
        account.setProfile(
                new Profile("Da Nang", "Asia/Ho_Chi_Minh")
        );
        account.getPreferences().put("theme", "light");
        account.getPreferences().put("language", "vi");
        account.getTags().add("beta");
        account.getTags().add("newsletter");

        String patch = """
                {
                  "displayName": "Lan Nguyen",
                  "profile": {
                    "city": "Hue"
                  },
                  "preferences": {
                    "theme": "dark",
                    "notifications": "enabled"
                  },
                  "tags": ["premium"]
                }
                """;

        mapper.readerForUpdating(account).readValue(patch);

        System.out.println(
                mapper.writerWithDefaultPrettyPrinter()
                        .writeValueAsString(account)
        );
    }
}
~~~

Kết quả thể hiện các quy tắc:

- displayName là scalar nên được thay bằng giá trị mới.
- profile được cập nhật tại chỗ; timezone cũ được giữ.
- preferences được hợp nhất theo key; language cũ được giữ.
- tags nhận thêm phần tử premium ở cuối.

Các property không xuất hiện trong JSON, chẳng hạn id, không bị cập nhật.

## 9. Cập nhật bằng ObjectMapper.updateValue

ObjectMapper.updateValue(valueToUpdate, overrides) là API tiện ích để áp dụng một object chứa các giá trị ghi đè lên object hiện tại:

~~~java
Account overrides = new Account();
overrides.setDisplayName("Lan Nguyen");
overrides.setProfile(new Profile("Hue", null));

mapper.updateValue(account, overrides);
~~~

API này hữu ích khi dữ liệu cập nhật đã nằm trong một object Java thay vì JSON string. Cách áp dụng merge vẫn phụ thuộc metadata merge và deserializer của property. Khi cần xác định rõ nguồn đầu vào là JSON và muốn quan sát quá trình binding, readerForUpdating thường thể hiện ý định trực tiếp hơn.

Không nhầm updateValue với việc gọi setter thủ công. Jackson vẫn dùng cơ chế serializer/deserializer và cấu hình mapper để áp dụng override. Hãy kiểm thử các property có JsonMerge, null policy và custom deserializer trong đúng luồng update mà ứng dụng dùng.

## 10. Null, property thiếu và merge

JsonMerge không làm cho null, missing và value trở thành cùng một trạng thái. Cần phân biệt:

| JSON đầu vào | Ý nghĩa trong update |
|---|---|
| Property không xuất hiện | Không có dữ liệu cập nhật cho property; giá trị hiện tại thường được giữ |
| Property có giá trị null | Xử lý theo null policy; mặc định thường có thể thay giá trị hiện tại bằng null |
| Property có object/Map/Collection | Áp dụng merge nếu property được đánh dấu và kiểu hỗ trợ |
| Property có scalar | Thay giá trị hiện tại bằng scalar mới |

Ví dụ:

~~~java
@JsonMerge
private Profile profile;
~~~

Với JSON không có profile, object hiện tại được giữ. Với JSON {"profile": null}, giá trị profile thường được đặt thành null theo null handling mặc định. Với JSON {"profile": {"city": "Hue"}}, object Profile hiện có được cập nhật.

Nếu muốn null tường minh không xóa object hiện tại, có thể kết hợp JsonSetter(nulls = Nulls.SKIP):

~~~java
@JsonMerge
@JsonSetter(nulls = Nulls.SKIP)
private Profile profile;
~~~

Khi đó, explicit null được bỏ qua theo null policy, còn object không null vẫn được merge. Đây là chính sách riêng của property; hãy kiểm thử nó cùng với JsonMerge.

## 11. JsonMerge không phải JSON Merge Patch (RFC 7396)

Tên JsonMerge dễ khiến người đọc nhầm với chuẩn HTTP JSON Merge Patch (RFC 7396). Đây là hai khái niệm khác nhau:

- JsonMerge là annotation Jackson điều khiển cách một property được hợp nhất trong thao tác update object.
- JSON Merge Patch là định dạng patch chuẩn hóa cho HTTP. Theo RFC 7396, object được hợp nhất đệ quy, member có giá trị null biểu thị xóa member, còn array được thay thế như một giá trị hoàn chỉnh.

So sánh:

| Hành vi | Jackson JsonMerge | JSON Merge Patch (RFC 7396) |
|---|---|---|
| Phạm vi | Property được đánh dấu trong update operation | Thuật toán áp dụng lên JSON document |
| Object | Deserializer cập nhật object hiện có | Hợp nhất member đệ quy |
| Map | Hợp nhất entry theo key | Member null xóa key tương ứng |
| Collection | Có thể nối phần tử vào collection hiện tại | Array mới thay thế array cũ |
| Null | Theo null provider/null policy của Jackson | Null trong object patch có nghĩa xóa member |
| Scalar | Thay giá trị | Thay giá trị |

Vì khác semantics, không nên dùng JsonMerge rồi tuyên bố API đã triển khai RFC 7396. Nếu endpoint công bố JSON Merge Patch, cần áp dụng thuật toán hoặc thư viện thực hiện đúng chuẩn, bao gồm quy tắc xóa member và thay thế array.

## 12. Merge không tự tạo thao tác xóa

Một payload merge thường chỉ nói rõ những giá trị muốn thêm hoặc cập nhật. Sự vắng mặt của một key không có nghĩa key đó phải bị xóa:

~~~json
{
  "preferences": {
    "theme": "dark"
  }
}
~~~

Với Map merge, key language cũ vẫn còn vì payload không nhắc đến nó.

Nếu cần xóa key, có thể:

- Gọi logic domain để xóa key theo một danh sách lệnh xóa riêng.
- Dùng một DTO patch có trường removeKeys.
- Dùng JSON Patch hoặc JSON Merge Patch nếu API muốn theo chuẩn tương ứng.
- Dùng một endpoint chuyên biệt cho thao tác xóa.

Không nên tự hiểu null là xóa key nếu hợp đồng hiện tại định nghĩa null là một giá trị hợp lệ. Hãy quy định rõ ý nghĩa của null và thao tác xóa.

## 13. Merge lồng nhau không mặc nhiên là deep merge vô hạn

Giả sử Account có Profile, Profile lại chứa một object Address:

~~~java
public class Profile {
    private String city;

    @JsonMerge
    private Address address;

    // getters/setters
}
~~~

~~~java
public class Address {
    private String street;
    private String ward;

    // getters/setters
}
~~~

Nếu muốn address được cập nhật từng phần, property address cũng cần có chính sách merge phù hợp. Annotation trên Account.profile xác định cách Jackson cập nhật Profile; nó không nên được xem là một cam kết rằng mọi object con ở mọi cấp đều được merge theo cùng cách.

Hãy đặt annotation tại từng ranh giới cần giữ cấu trúc cũ và kiểm thử payload lồng nhau. Điều này giúp tránh việc một phần dữ liệu bị thay thế ngoài ý muốn hoặc ngược lại, một phần dữ liệu cũ được giữ lại khi nghiệp vụ muốn thay mới hoàn toàn.

## 14. Giới hạn và điều kiện để merge hoạt động

Một số điểm cần cân nhắc:

- Property phải được Jackson nhận diện và có giá trị hiện tại để hợp nhất.
- Kiểu dữ liệu phải có deserializer hỗ trợ cập nhật vào giá trị hiện có.
- POJO thường cần một cách để Jackson cập nhật các property, chẳng hạn setter hoặc field có thể truy cập theo cấu hình.
- Collection phải là kiểu có thể thay đổi nếu muốn nối thêm phần tử.
- Một collection bất biến hoặc không hỗ trợ add có thể không phù hợp với merge tại chỗ.
- Nếu giá trị hiện tại là null, Jackson không thể cập nhật một instance chưa tồn tại; nó phải tạo giá trị mới theo deserializer.
- Custom deserializer phải hỗ trợ đường xử lý update nếu muốn tham gia merge; không phải mọi deserializer đều có thể cập nhật giá trị cũ.

Nếu JsonMerge không tạo kết quả mong đợi, hãy kiểm tra kiểu property, giá trị hiện tại, mutability của collection, custom deserializer và API update đang được gọi.

## 15. Kiểm thử replace và merge

Nên kiểm thử cùng một payload với hai mô hình: một property không có JsonMerge và một property có annotation. Nhờ đó, khác biệt được thể hiện rõ qua kết quả.

Ma trận kiểm thử:

| Ca | Giá trị hiện tại | JSON cập nhật | Kết quả mong đợi khi merge |
|---|---|---|---|
| POJO partial | city và timezone đều có | Chỉ gửi city mới | City đổi, timezone giữ |
| Map partial | theme và language có | Chỉ gửi theme mới | Theme đổi, language giữ |
| Map thêm key | theme có | Gửi notifications | Key notifications được thêm |
| List append | [beta, newsletter] | [premium] | [beta, newsletter, premium] |
| Scalar update | displayName = Lan | displayName = Lan Nguyen | Thay bằng Lan Nguyen |
| Property missing | profile có dữ liệu | Không gửi profile | Giữ profile hiện tại |
| Explicit null | profile có dữ liệu | profile = null | Theo null policy; mặc định thường đặt null |
| Collection duplicate | [beta] | [beta] | Có thể thành [beta, beta]; không tự dedupe |
| Array | Mảng hiện tại | Mảng mới | Thay array; không nối như Collection |

Ví dụ test JUnit cho POJO:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JsonMergeTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void mergesNestedPojoAndPreservesMissingField() throws Exception {
        Account account = new Account();
        account.setProfile(
                new Profile("Da Nang", "Asia/Ho_Chi_Minh")
        );

        mapper.readerForUpdating(account).readValue("""
                {
                  "profile": {
                    "city": "Hue"
                  }
                }
                """);

        assertEquals("Hue", account.getProfile().getCity());
        assertEquals(
                "Asia/Ho_Chi_Minh",
                account.getProfile().getTimezone()
        );
    }

    @Test
    void mergesMapEntriesInsteadOfReplacingWholeMap() throws Exception {
        Account account = new Account();
        account.getPreferences().put("theme", "light");
        account.getPreferences().put("language", "vi");

        mapper.readerForUpdating(account).readValue("""
                {
                  "preferences": {
                    "theme": "dark"
                  }
                }
                """);

        assertEquals("dark", account.getPreferences().get("theme"));
        assertEquals("vi", account.getPreferences().get("language"));
    }

    @Test
    void appendsIncomingCollectionElements() throws Exception {
        Account account = new Account();
        account.getTags().add("beta");

        mapper.readerForUpdating(account).readValue("""
                {
                  "tags": ["premium"]
                }
                """);

        assertEquals(
                List.of("beta", "premium"),
                account.getTags()
        );
    }
}
~~~

Các test trên giả định Account đã khai báo JsonMerge trên profile, preferences và tags như ví dụ trước. Hãy chạy trên phiên bản Jackson thực tế của ứng dụng vì loại deserializer và kiểu collection có thể ảnh hưởng chi tiết update.

## 16. Khi nào nên dùng replace, khi nào nên dùng merge?

| Nhu cầu | Cách phù hợp |
|---|---|
| Client gửi toàn bộ object con và muốn thay mới | Replace |
| Client chỉ gửi vài field của object con, cần giữ phần còn lại | JsonMerge |
| Cập nhật Map theo từng key | JsonMerge trên Map |
| Thêm phần tử vào Collection hiện tại | JsonMerge trên Collection có thể thay đổi |
| Thay toàn bộ danh sách theo payload | Replace |
| Cập nhật phần tử Collection theo ID | Logic domain hoặc custom update |
| Xóa key Map theo semantics HTTP chuẩn | JSON Merge Patch hoặc logic xóa tường minh |
| Cần xóa một phần tử array theo index | JSON Patch hoặc thao tác domain |
| Null phải có nghĩa bỏ qua | JsonSetter(nulls = Nulls.SKIP) kết hợp merge nếu phù hợp |

Hãy chọn theo ý nghĩa nghiệp vụ, không chỉ theo cấu trúc Java. Ví dụ, một danh sách vai trò có thể cần thay thế toàn bộ để tránh giữ quyền cũ; trong khi một Map tùy chọn giao diện có thể phù hợp với merge theo key.

## 17. Kết luận

JsonMerge yêu cầu Jackson hợp nhất giá trị JSON vào cấu trúc đang tồn tại trong thao tác update thay vì thay thế toàn bộ property. Với POJO lồng nhau, các field được gửi được cập nhật và field bị thiếu được giữ lại; với Map, entry được hợp nhất theo key; với Collection, phần tử đầu vào thường được nối vào collection hiện tại. Scalar vẫn được thay thế và Java array không được merge như Collection. Property bị thiếu thường không thay đổi; explicit null vẫn theo null policy và có thể đặt giá trị hiện tại thành null. JsonMerge không đồng nghĩa JSON Merge Patch RFC 7396: hai cơ chế có quy tắc khác nhau về array, null và xóa key. Hãy đánh dấu đúng property, chọn rõ null/removal semantics và kiểm thử cả replace lẫn merge trên payload thực tế.
