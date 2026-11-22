# Kiểm thử ngày giờ với nhiều múi giờ và độ chính xác

Ngày giờ là một trong những nhóm dữ liệu dễ phát sinh lỗi khi serialize và deserialize. Một giá trị có thể biểu diễn một thời điểm tuyệt đối, một giờ địa phương, một offset UTC hoặc một múi giờ có quy tắc lịch sử và DST. Những khái niệm này không thể thay thế cho nhau.

Một test chỉ xác nhận JSON đọc lại được chưa đủ. Test cần xác nhận điều gì được bảo toàn: cùng instant, cùng local date-time, cùng offset, cùng region ZoneId hay cùng độ chính xác đến nano/micro/millisecond. Nếu mapper tự điều chỉnh về timezone cấu hình, nếu timestamp bị hiểu nhầm là giây thay vì millisecond, hoặc nếu độ chính xác bị cắt, JSON vẫn có thể hợp lệ nhưng kết quả nghiệp vụ đã thay đổi.

Bài học này tập trung vào cách thiết kế test Jackson cho nhiều múi giờ, các thời điểm chuyển DST và độ chính xác của dữ liệu thời gian.

## 1. Phân biệt các kiểu ngày giờ của Java

Trước khi viết test, hãy chọn kiểu Java đúng với ý nghĩa dữ liệu:

| Kiểu | Lưu thông tin gì? | Có xác định một instant duy nhất? |
|---|---|---|
| LocalDate | Ngày lịch, không có giờ hoặc zone | Không |
| LocalTime | Giờ trong ngày, không có ngày hoặc zone | Không |
| LocalDateTime | Ngày và giờ trên đồng hồ địa phương, không có offset/zone | Không |
| OffsetDateTime | Ngày giờ cùng UTC offset, ví dụ +07:00 | Có |
| ZonedDateTime | Ngày giờ cùng ZoneId vùng, ví dụ Asia/Ho_Chi_Minh | Có |
| Instant | Một thời điểm trên trục thời gian UTC | Có |
| Duration | Khoảng thời gian theo giây và nano | Không phải ngày giờ lịch |
| Period | Khoảng thời gian theo năm, tháng, ngày lịch | Không phải số giây cố định |

LocalDateTime 09:00 không đủ thông tin để xác định đó là 09:00 ở Hà Nội, Paris hay New York. Không nên tự gắn timezone hệ điều hành vào một LocalDateTime trừ khi contract xác định rõ zone.

OffsetDateTime có offset cụ thể nhưng không mang toàn bộ quy tắc của một vùng địa lý. Ví dụ +01:00 chỉ cho biết độ lệch tại thời điểm đó. Nó không cho biết vùng đó có chuyển sang +02:00 vào mùa hè hay không.

ZonedDateTime mang ZoneId như Europe/Paris. ZoneId tra cứu quy tắc theo ngày trong cơ sở dữ liệu timezone của JDK. Đây là lựa chọn phù hợp khi nghiệp vụ cần giữ danh tính vùng và áp dụng quy tắc DST.

Instant phù hợp khi cần lưu một thời điểm tuyệt đối như lúc tạo event, lúc thanh toán hoặc thời điểm ghi log. Có thể chuyển Instant sang các vùng khác nhau để hiển thị mà không làm thay đổi instant.

## 2. Đăng ký JavaTimeModule cho Jackson

Các kiểu java.time cần module JSR-310 của Jackson:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
~~~

Giữ version module cùng version line với Jackson Databind/Core; nếu dự án dùng Jackson BOM thì để BOM quản lý phiên bản.

Tạo mapper dùng cho test:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
        .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
        .build();
~~~

Các cấu hình trên có ý nghĩa:

- JavaTimeModule đăng ký serializer/deserializer cho các kiểu java.time.
- WRITE_DATES_AS_TIMESTAMPS bị tắt để ghi ngày giờ dạng ISO-8601 text thay vì timestamp/array.
- ADJUST_DATES_TO_CONTEXT_TIME_ZONE bị tắt để các kiểu có offset/zone giữ thông tin vùng/offset đầu vào khi phù hợp với kiểu đích.
- WRITE_DATES_WITH_ZONE_ID được bật để ZonedDateTime có thể ghi cả region ZoneId trong biểu diễn text.

Không phải ứng dụng nào cũng nên dùng cùng cấu hình này. Đây là cấu hình test minh họa cho contract cần giữ ZoneId và offset. Nếu API chủ đích chuẩn hóa mọi timestamp về UTC, hãy cấu hình và test theo contract UTC đó.

Framework như Spring Boot có thể cấu hình mapper khác mapper tạo bằng new ObjectMapper(). Test tích hợp nên dùng chính mapper bean production để bắt được khác biệt về module và feature.

## 3. ISO-8601 text và timestamp là hai contract khác nhau

Khi WRITE_DATES_AS_TIMESTAMPS tắt, các kiểu java.time thường được ghi thành chuỗi ISO-8601 phù hợp với kiểu. Ví dụ:

~~~json
{
  "instant": "2026-11-12T10:30:00.123456789Z",
  "localDate": "2026-11-12",
  "localDateTime": "2026-11-12T17:30:00",
  "offsetDateTime": "2026-11-12T17:30:00+07:00",
  "zonedDateTime": "2026-11-12T17:30:00+07:00[Asia/Ho_Chi_Minh]"
}
~~~

Biểu diễn cụ thể phụ thuộc kiểu Java và feature cấu hình. LocalDateTime không tự thêm Z hoặc offset vì bản thân nó không có timezone.

Khi WRITE_DATES_AS_TIMESTAMPS bật, một số kiểu local có thể được ghi thành array thành phần ngày/giờ; các kiểu dựa trên instant có thể được ghi thành số. Định dạng timestamp có thể phụ thuộc WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS.

Đừng chỉ kiểm tra rằng output là JSON hợp lệ. Hãy kiểm tra đúng representation mà API công bố: ISO string, epoch milliseconds, epoch seconds hay array. Consumer có thể hiểu sai đơn vị dù JSON number vẫn hợp lệ.

## 4. Kiểm thử Instant: bảo toàn thời điểm tuyệt đối

Instant không chứa timezone hiển thị. Nó biểu diễn một điểm duy nhất trên timeline. Cùng một Instant có thể được hiển thị ở nhiều ZoneId nhưng giá trị Instant không đổi.

~~~java
@Test
void preservesInstantWhenRoundTrippingIsoText() throws Exception {
    Instant source = Instant.parse("2026-11-12T10:30:00.123456789Z");

    String json = mapper.writeValueAsString(source);
    Instant restored = mapper.readValue(json, Instant.class);

    assertEquals(source, restored);
}
~~~

Test này xác nhận cả thời điểm và phần nano được giữ nguyên với cấu hình ISO text.

Nếu ứng dụng chuyển một Instant sang ZonedDateTime để hiển thị:

~~~java
Instant instant = Instant.parse("2026-11-12T10:30:00Z");

ZonedDateTime inParis = instant.atZone(ZoneId.of("Europe/Paris"));
ZonedDateTime inHcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(inParis.toInstant(), inHcm.toInstant());
assertNotEquals(inParis.getOffset(), inHcm.getOffset());
~~~

Local date-time và offset có thể khác nhau, nhưng instant phải bằng nhau. Đây là invariant quan trọng khi kiểm thử chuyển đổi timezone.

## 5. Kiểm thử LocalDateTime: không tự gán timezone

LocalDateTime chỉ giữ các thành phần lịch/đồng hồ. Jackson không thể suy ra một instant duy nhất từ nó.

~~~java
@Test
void preservesLocalDateTimeFields() throws Exception {
    LocalDateTime source = LocalDateTime.of(
            2026, 11, 12, 17, 30, 0, 123_456_789
    );

    String json = mapper.writeValueAsString(source);
    LocalDateTime restored = mapper.readValue(json, LocalDateTime.class);

    assertEquals(source, restored);
}
~~~

Không nên test LocalDateTime bằng cách so sánh epoch milliseconds nếu chưa chọn ZoneId. Chuyển nó thành Instant đòi hỏi một vùng và có thể gặp DST gap/overlap.

Nếu API nhận giờ họp địa phương, contract nên có thêm zone ID hoặc offset riêng, ví dụ:

~~~json
{
  "localDateTime": "2026-11-12T17:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Sau đó ứng dụng mới kết hợp hai field theo quy tắc nghiệp vụ. Không nên dựa vào timezone mặc định của server.

## 6. Kiểm thử OffsetDateTime: giữ offset hoặc chuẩn hóa UTC

OffsetDateTime mang local date-time cùng offset. Khi đọc, Jackson có thể điều chỉnh giá trị theo timezone cấu hình của mapper nếu ADJUST_DATES_TO_CONTEXT_TIME_ZONE được bật.

Ví dụ test giữ offset:

~~~java
@Test
void preservesOffsetDateTimeWhenContextAdjustmentIsDisabled()
        throws Exception {
    OffsetDateTime source =
            OffsetDateTime.parse("2026-11-12T17:30:00.123456789+07:00");

    String json = mapper.writeValueAsString(source);
    OffsetDateTime restored =
            mapper.readValue(json, OffsetDateTime.class);

    assertEquals(source, restored);
    assertEquals(ZoneOffset.ofHours(7), restored.getOffset());
    assertEquals(source.toInstant(), restored.toInstant());
}
~~~

Nếu contract yêu cầu mọi thời điểm được chuẩn hóa về UTC, hãy test điều đó riêng:

~~~java
OffsetDateTime source =
        OffsetDateTime.parse("2026-11-12T17:30:00+07:00");

OffsetDateTime normalized =
        source.withOffsetSameInstant(ZoneOffset.UTC);

assertEquals(source.toInstant(), normalized.toInstant());
assertEquals(ZoneOffset.UTC, normalized.getOffset());
~~~

Phân biệt withOffsetSameInstant và withOffsetSameLocal:

- withOffsetSameInstant đổi offset nhưng giữ nguyên thời điểm tuyệt đối; local clock time có thể đổi.
- withOffsetSameLocal giữ local clock time nhưng đổi offset; instant có thể đổi.

Đây là hai thao tác khác nhau. Test nên khẳng định rõ invariant cần giữ để tránh chọn nhầm API.

## 7. Kiểm thử ZonedDateTime: giữ cả ZoneId và instant

ZonedDateTime chứa LocalDateTime, ZoneOffset và ZoneId. Khi serialize chỉ có offset, region ID như Europe/Paris có thể bị mất. WRITE_DATES_WITH_ZONE_ID cho phép đưa zone ID vào biểu diễn text.

~~~java
@Test
void preservesRegionZoneAndInstant() throws Exception {
    ZoneId zone = ZoneId.of("Europe/Paris");
    ZonedDateTime source = ZonedDateTime.of(
            2026, 7, 1, 12, 30, 0, 123_456_789, zone
    );

    String json = mapper.writeValueAsString(source);
    ZonedDateTime restored = mapper.readValue(json, ZonedDateTime.class);

    assertEquals(source, restored);
    assertEquals(zone, restored.getZone());
    assertEquals(source.toInstant(), restored.toInstant());
}
~~~

Với zone ID được ghi, JSON có thể có dạng:

~~~json
"2026-07-01T12:30:00.123456789+02:00[Europe/Paris]"
~~~

Kết quả offset phụ thuộc ngày và quy tắc timezone database. Đừng hardcode một offset chung cho cả năm của một vùng có DST.

Nếu WRITE_DATES_WITH_ZONE_ID tắt, output có thể chỉ còn offset, ví dụ +02:00. Khi đọc lại, ứng dụng có thể chỉ khôi phục offset đó thay vì region ZoneId ban đầu. Nếu nghiệp vụ cần quy tắc vùng cho những ngày tương lai, giữ ZoneId là điều cần thiết.

## 8. ADJUST_DATES_TO_CONTEXT_TIME_ZONE ảnh hưởng điều gì?

ADJUST_DATES_TO_CONTEXT_TIME_ZONE điều khiển việc điều chỉnh kiểu ngày giờ có timezone/offset theo timezone trong DeserializationContext. Feature này thường được bật mặc định trong Jackson Databind. Khi bật, offset hoặc region đầu vào có thể được chuyển sang context timezone; instant có thể vẫn giữ nhưng offset/zone được biểu diễn sau deserialize có thể khác.

Ví dụ, input có offset +07:00 được đọc trong context UTC có thể được biểu diễn lại bằng offset UTC. Điều này không nhất thiết làm thay đổi instant, nhưng có thể làm mất thông tin offset ban đầu.

Nếu contract yêu cầu giữ offset/region từ payload, tắt feature cho mapper/reader phù hợp:

~~~java
ObjectMapper preservingMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
        .build();
~~~

Nếu contract yêu cầu chuẩn hóa, cấu hình context timezone rõ ràng và test kết quả chuẩn hóa. Không dựa vào timezone mặc định của máy chạy test.

Đừng chỉ assert Instant bằng nhau nếu contract còn yêu cầu giữ ZoneId hoặc offset. Hãy assert riêng từng phần.

## 9. Dùng nhiều ZoneId trong cùng một bộ test

Nên kiểm thử cả UTC, vùng không có DST và vùng có DST:

~~~java
static Stream<Arguments> zoneCases() {
    return Stream.of(
            Arguments.of("UTC"),
            Arguments.of("Asia/Ho_Chi_Minh"),
            Arguments.of("Europe/Paris"),
            Arguments.of("America/New_York"),
            Arguments.of("Australia/Sydney")
    );
}

@ParameterizedTest
@MethodSource("zoneCases")
void roundTripsZonedDateTimeForRegion(String zoneName) throws Exception {
    ZoneId zone = ZoneId.of(zoneName);
    ZonedDateTime source = ZonedDateTime.of(
            2026, 6, 15, 9, 45, 30, 987_654_321, zone
    );

    String json = mapper.writeValueAsString(source);
    ZonedDateTime restored = mapper.readValue(json, ZonedDateTime.class);

    assertEquals(source, restored);
    assertEquals(zone, restored.getZone());
    assertEquals(source.toInstant(), restored.toInstant());
}
~~~

Ví dụ cần import JUnit 5 ParameterizedTest, MethodSource, Arguments và Stream. Ngày test được chọn phải phù hợp với các vùng cần kiểm tra; nếu cần xác nhận cả mùa đông và mùa hè, tạo hai bộ dữ liệu riêng.

Không dùng các abbreviation như CST, IST hoặc EST làm ZoneId trong contract. Chúng có thể mơ hồ hoặc không chứa đầy đủ quy tắc DST. Dùng tên IANA region như America/New_York hoặc Asia/Ho_Chi_Minh.

## 10. Kiểm thử DST gap: giờ địa phương không tồn tại

Ở vùng có DST, đồng hồ có thể nhảy tiến. Khi đó một khoảng local time không tồn tại.

Ví dụ tại America/New_York, ngày chuyển sang giờ mùa hè năm 2024, đồng hồ bỏ qua khoảng 02:00 đến trước 03:00. LocalDateTime 2024-03-10T02:30 không tồn tại trong vùng này.

~~~java
@Test
void detectsDaylightSavingGap() {
    ZoneId zone = ZoneId.of("America/New_York");
    LocalDateTime gapTime = LocalDateTime.of(2024, 3, 10, 2, 30);

    ZoneRules rules = zone.getRules();
    List<ZoneOffset> validOffsets = rules.getValidOffsets(gapTime);
    ZoneOffsetTransition transition = rules.getTransition(gapTime);

    assertTrue(validOffsets.isEmpty());
    assertNotNull(transition);
    assertTrue(transition.isGap());
}
~~~

Khi tạo ZonedDateTime từ LocalDateTime trong gap, Java có thể điều chỉnh giờ tiến qua khoảng gap theo quy tắc của API. Điều đó có thể hợp lệ về kỹ thuật nhưng không phải lúc nào cũng đúng nghiệp vụ.

Với lịch hẹn, giờ làm hoặc deadline, ứng dụng có thể cần từ chối giờ không tồn tại thay vì tự động đẩy sang giờ khác. Test nên khóa chính sách này.

## 11. Kiểm thử DST overlap: một giờ địa phương có hai offset

Khi đồng hồ lùi lại, một khoảng local time có thể xuất hiện hai lần. Khi đó một LocalDateTime có hai offset hợp lệ và tương ứng với hai instant khác nhau.

Ví dụ America/New_York ngày 2024-11-03 có giờ 01:30 xuất hiện hai lần:

~~~java
@Test
void detectsDaylightSavingOverlap() {
    ZoneId zone = ZoneId.of("America/New_York");
    LocalDateTime overlapTime = LocalDateTime.of(2024, 11, 3, 1, 30);

    List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(overlapTime);

    assertEquals(2, offsets.size());

    ZonedDateTime first =
            ZonedDateTime.ofLocal(overlapTime, zone, offsets.get(0));
    ZonedDateTime second =
            ZonedDateTime.ofLocal(overlapTime, zone, offsets.get(1));

    assertEquals(overlapTime, first.toLocalDateTime());
    assertEquals(overlapTime, second.toLocalDateTime());
    assertNotEquals(first.getOffset(), second.getOffset());
    assertNotEquals(first.toInstant(), second.toInstant());
}
~~~

Hai ZonedDateTime có cùng local clock time nhưng khác offset và khác instant. Một API chỉ nhận LocalDateTime không thể biết người dùng muốn lần 01:30 thứ nhất hay thứ hai.

Nếu nghiệp vụ cần phân biệt, request phải cung cấp offset, instant hoặc một lựa chọn rõ ràng về occurrence. Test phải xác nhận chính sách khi overlap, không chỉ xác nhận parse thành công.

## 12. Test quy tắc DST bằng ZoneRules thay vì hardcode mọi offset

Có thể kiểm tra vùng và ngày bằng ZoneRules:

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");

LocalDateTime winter = LocalDateTime.of(2026, 1, 15, 12, 0);
LocalDateTime summer = LocalDateTime.of(2026, 7, 15, 12, 0);

ZoneOffset winterOffset = paris.getRules().getOffset(winter);
ZoneOffset summerOffset = paris.getRules().getOffset(summer);

assertNotEquals(winterOffset, summerOffset);
~~~

Test này kiểm tra vùng có offset khác nhau giữa hai thời điểm đã chọn. Khi viết test nghiệp vụ, có thể assert offset cụ thể nếu đó là contract cần kiểm tra, nhưng hãy nhận thức rằng timezone database có thể được cập nhật theo thay đổi luật pháp.

Các quy tắc tương lai có thể đổi sau khi JDK cập nhật tzdb. Nếu test phải tái lập tuyệt đối, pin JDK/runtime image và cập nhật expected values có kiểm soát. Đối với ngày lịch sử đã xác nhận, dữ liệu thường ổn định hơn nhưng vẫn nên ghi rõ môi trường test.

## 13. Kiểm thử độ chính xác đến nano

Instant và các kiểu java.time có độ chính xác nanosecond. Ví dụ:

~~~java
@Test
void preservesNanosecondPrecisionWithIsoText() throws Exception {
    Instant source =
            Instant.parse("2026-11-12T10:30:00.123456789Z");

    String json = mapper.writeValueAsString(source);
    Instant restored = mapper.readValue(json, Instant.class);

    assertEquals(source, restored);
    assertEquals(123_456_789, restored.getNano());
}
~~~

Không chỉ assert giây hoặc epoch milliseconds. Nếu chỉ so sánh toEpochMilli(), test có thể bỏ sót việc 456.789 nano bị cắt.

Các mức thường gặp:

| Kiểu/lưu trữ | Độ chính xác thường có |
|---|---|
| Instant | Nanosecond |
| LocalDateTime | Nanosecond |
| OffsetDateTime | Nanosecond |
| ZonedDateTime | Nanosecond |
| java.util.Date | Millisecond |
| Một số database column | Millisecond hoặc microsecond tùy loại/cấu hình |
| Hệ thống epoch millis | Millisecond |

Nếu database chỉ giữ microsecond, round-trip qua database có thể làm mất ba chữ số nano cuối. Test tích hợp phải xác nhận precision thực tế của database và driver, không chỉ Jackson.

## 14. Timestamp seconds và milliseconds

Khi dùng numeric timestamp, cần xác định rõ đơn vị. Một số feature của Java Time module ảnh hưởng cách đọc/ghi timestamp:

- SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS: khi ghi timestamp cho kiểu hỗ trợ, điều khiển biểu diễn độ chính xác nano so với millisecond.
- DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS: điều khiển cách diễn giải integer timestamp; với Java Time module, integer có thể được hiểu là seconds hoặc milliseconds theo feature.
- Giá trị decimal timestamp biểu diễn seconds cùng phần thập phân của giây.

Ví dụ mapper ghi Instant dưới dạng timestamp:

~~~java
ObjectMapper secondsMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .enable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .enable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
~~~

Mapper dùng integer milliseconds:

~~~java
ObjectMapper millisMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .disable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
~~~

Tên feature có chữ DATE dù được dùng cho các kiểu Java time trong module. Kiểm tra đúng version Jackson đang dùng và test output thực tế cho kiểu cụ thể.

Không trao đổi numeric timestamp nếu contract không nói rõ seconds hay milliseconds. Một giá trị như 1_800_000_000 có thể mang ý nghĩa rất khác nếu hai phía dùng đơn vị khác nhau.

## 15. Test timestamp milliseconds và phần precision bị mất

Ví dụ test một Instant có phần nano không chia hết cho millisecond:

~~~java
@Test
void documentsPrecisionLossWhenUsingEpochMilliseconds()
        throws Exception {
    Instant source =
            Instant.parse("2026-11-12T10:30:00.123456789Z");

    String json = millisMapper.writeValueAsString(source);
    Instant restored = millisMapper.readValue(json, Instant.class);

    Instant expected = Instant.ofEpochMilli(source.toEpochMilli());

    assertEquals(expected, restored);
    assertNotEquals(source, restored);
}
~~~

Test này không khẳng định mất precision là lỗi trong mọi hệ thống. Nó ghi nhận contract millisecond có chủ đích. Nếu API cần nano, hãy dùng ISO text hoặc timestamp có fractional seconds và test đầy đủ phần fraction.

Tránh chuyển timestamp qua double nếu cần giữ precision chính xác. Floating-point có giới hạn số chữ số thập phân biểu diễn chính xác. Với timestamp chính xác cao, dùng ISO string, integer units có quy ước rõ hoặc decimal representation được xử lý bằng BigDecimal.

## 16. Kiểm tra phần fraction với nhiều độ dài

Một bộ test tốt nên bao gồm thời điểm không có fraction, fraction millisecond, microsecond và nanosecond:

~~~java
static Stream<String> instantSamples() {
    return Stream.of(
            "2026-11-12T10:30:00Z",
            "2026-11-12T10:30:00.123Z",
            "2026-11-12T10:30:00.123456Z",
            "2026-11-12T10:30:00.123456789Z"
    );
}

@ParameterizedTest
@MethodSource("instantSamples")
void readsAndWritesInstantSamples(String text) throws Exception {
    Instant source = Instant.parse(text);

    String json = mapper.writeValueAsString(source);
    Instant restored = mapper.readValue(json, Instant.class);

    assertEquals(source, restored);
}
~~~

ISO formatter có thể bỏ các số zero cuối trong fraction khi serialize. Vì vậy, nếu contract yêu cầu biểu diễn lexical cố định đúng chín chữ số, cần formatter/serializer có pattern cố định và test chuỗi chính xác. Nếu contract chỉ yêu cầu cùng giá trị thời gian, hãy so sánh Instant thay vì yêu cầu text có cùng số lượng số 0.

## 17. Kiểm thử LocalDate, LocalTime và biên ngày

Ngày và giờ địa phương không có zone nhưng vẫn có các trường hợp biên quan trọng:

- Ngày cuối tháng và đầu tháng.
- Ngày nhuận 29/02.
- Cuối năm và đầu năm.
- Midnight.
- Giờ có phần nano.
- Giá trị ngoài range nghiệp vụ.

Ví dụ:

~~~java
@ParameterizedTest
@ValueSource(strings = {
        "2024-02-29",
        "2026-01-01",
        "2026-12-31"
})
void roundTripsLocalDate(String text) throws Exception {
    LocalDate source = LocalDate.parse(text);

    String json = mapper.writeValueAsString(source);
    LocalDate restored = mapper.readValue(json, LocalDate.class);

    assertEquals(source, restored);
}
~~~

Với LocalTime:

~~~java
@Test
void preservesLocalTimeFraction() throws Exception {
    LocalTime source = LocalTime.of(23, 59, 59, 999_999_999);

    String json = mapper.writeValueAsString(source);
    LocalTime restored = mapper.readValue(json, LocalTime.class);

    assertEquals(source, restored);
}
~~~

Không chuyển LocalDate thành Instant nếu nghiệp vụ chỉ lưu ngày sinh, ngày hóa đơn hoặc ngày nghỉ. Việc gắn zone có thể làm ngày thay đổi khi chuyển qua UTC hoặc vùng khác.

## 18. Dùng Clock cố định để test logic hiện tại

Không gọi LocalDate.now() hoặc Instant.now() trực tiếp trong logic cần test nếu có thể inject Clock. Thời điểm hệ thống khiến test phụ thuộc ngày chạy và timezone mặc định.

Ví dụ service:

~~~java
public class ExpiryService {
    private final Clock clock;

    public ExpiryService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
~~~

Test:

~~~java
@Test
void evaluatesExpiryAtFixedInstant() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-12T10:30:00Z"),
            ZoneId.of("UTC")
    );

    ExpiryService service = new ExpiryService(clock);

    assertTrue(service.isExpired(
            Instant.parse("2026-11-12T10:29:59Z")
    ));
    assertFalse(service.isExpired(
            Instant.parse("2026-11-12T10:30:01Z")
    ));
}
~~~

Clock.fixed làm thời điểm hiện tại không thay đổi giữa các lần chạy. Nếu nghiệp vụ cần ngày địa phương, tạo Clock với ZoneId phù hợp và test zone được inject, thay vì dựa vào ZoneId.systemDefault().

## 19. Kiểm thử @JsonFormat khi contract yêu cầu pattern riêng

@JsonFormat có thể dùng để quy định pattern, shape, locale hoặc timezone cho property:

~~~java
public record Appointment(
        @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
        OffsetDateTime startsAt
) {}
~~~

Pattern XXX biểu diễn offset như +07:00. Hãy dùng formatter phù hợp với kiểu dữ liệu và contract. Không dùng pattern thiếu offset cho dữ liệu cần xác định instant.

Nếu pattern chỉ có ngày và giờ local mà không có offset, deserialize thành LocalDateTime là rõ ràng hơn. Nếu target là Instant hoặc OffsetDateTime, input cần có thông tin đủ để xác định instant hoặc phải có quy tắc timezone rõ.

Test annotation bằng đúng mapper production:

~~~java
@Test
void followsAppointmentPattern() throws Exception {
    Appointment appointment = new Appointment(
            OffsetDateTime.parse("2026-11-12T17:30:00+07:00")
    );

    String json = mapper.writeValueAsString(appointment);
    Appointment restored = mapper.readValue(json, Appointment.class);

    assertEquals(appointment.startsAt(), restored.startsAt());
}
~~~

@JsonFormat timezone có thể tác động cách diễn giải hoặc hiển thị tùy kiểu và serializer/deserializer. Đừng thêm timezone annotation chỉ để làm test pass; xác định contract trước rồi assert offset/instant tương ứng.

## 20. Kiểm tra timezone mặc định của mapper và JVM

Một test có thể pass trên máy developer nhưng fail trong CI nếu mapper phụ thuộc timezone mặc định của JVM. Hãy cấu hình timezone tường minh nếu context timezone là một phần contract:

~~~java
ObjectMapper utcMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

utcMapper.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

Đối với các kiểu java.time, hãy kiểm tra cả ADJUST_DATES_TO_CONTEXT_TIME_ZONE và timezone context. Với legacy Date/Calendar, timezone context cũng ảnh hưởng cách format/parse.

Tránh thay đổi TimeZone.setDefault() trong test suite vì đây là trạng thái global của JVM và có thể làm test chạy song song ảnh hưởng lẫn nhau. Nếu bắt buộc kiểm tra hành vi phụ thuộc system default, chạy test cô lập trong process riêng và khôi phục trạng thái cẩn thận.

## 21. Kiểm thử dữ liệu sai và ngày giờ không hợp lệ

Một test nên bao gồm:

- Tháng/ngày không tồn tại, ví dụ 2026-02-30.
- Giờ ngoài range, ví dụ 25:10.
- Offset sai định dạng.
- Timestamp ngoài range kiểu đích.
- Local time nằm trong DST gap.
- Region ID không tồn tại.
- Precision vượt giới hạn mà hệ thống đích hỗ trợ.
- Input thiếu offset khi contract yêu cầu offset.

Ví dụ:

~~~java
@Test
void rejectsInvalidLocalDate() {
    assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue("\"2026-02-30\"", LocalDate.class)
    );
}
~~~

Exception cụ thể có thể được bọc theo serializer/deserializer và version. Khi cần test loại lỗi chính xác, kiểm tra cause chain và exception path thay vì chỉ dựa vào thông báo text.

Đối với giờ DST gap, parse LocalDateTime có thể thành công vì LocalDateTime không biết zone. Lỗi chỉ xuất hiện khi ứng dụng kết hợp nó với ZoneId và áp dụng chính sách gap. Vì vậy, test parse và test domain conversion thành hai trường hợp riêng.

## 22. Test nhiều zone nhưng giữ cùng instant

Một cách kiểm tra tốt là chọn một Instant duy nhất rồi biểu diễn ở nhiều vùng:

~~~java
@Test
void sameInstantHasDifferentLocalRepresentations() {
    Instant instant = Instant.parse("2026-11-12T10:30:00Z");

    ZonedDateTime utc = instant.atZone(ZoneId.of("UTC"));
    ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
    ZonedDateTime paris = instant.atZone(ZoneId.of("Europe/Paris"));
    ZonedDateTime newYork = instant.atZone(ZoneId.of("America/New_York"));

    assertEquals(instant, utc.toInstant());
    assertEquals(instant, hcm.toInstant());
    assertEquals(instant, paris.toInstant());
    assertEquals(instant, newYork.toInstant());

    assertNotEquals(utc.toLocalDateTime(), hcm.toLocalDateTime());
}
~~~

Test này bảo đảm chuyển vùng chỉ thay đổi cách hiển thị local/offset, không làm đổi instant. Nếu code dùng withZoneSameLocal thay vì atZone/withZoneSameInstant, instant có thể thay đổi; test sẽ phát hiện lỗi đó.

## 23. Kiểm thử round-trip không phải lúc nào cũng đủ

Một test serialize rồi deserialize bằng cùng một mapper có thể pass dù JSON contract sai với consumer bên ngoài. Ví dụ writer xuất timestamp milliseconds và reader cùng mapper cũng hiểu milliseconds; hai phía round-trip vẫn thành công nhưng consumer khác hiểu seconds có thể sai lệch rất lớn.

Vì vậy, test nên có ba lớp:

1. **Value round-trip:** object -> JSON -> object, xác nhận kiểu/precision/zone cần giữ.
2. **Contract test:** assert JSON text/number/offset/ZoneId đúng format được công bố.
3. **Interoperability test:** đọc payload fixture do hệ thống ngoài tạo hoặc dùng reader cấu hình độc lập để xác nhận đơn vị và semantics.

Ví dụ contract test:

~~~java
@Test
void writesInstantAsIsoUtcString() throws Exception {
    Instant instant = Instant.parse("2026-11-12T10:30:00Z");

    String json = mapper.writeValueAsString(instant);

    assertEquals("\"2026-11-12T10:30:00Z\"", json);
}
~~~

Nếu format được phép thay đổi về số chữ số fraction, hãy assert parsed value hoặc dùng JSON parser thay vì so sánh raw string quá chặt.

## 24. Kiểm thử tương thích khi đổi cấu hình Jackson

Khi thay đổi các feature thời gian, hãy giữ fixture từ contract cũ:

- ISO text có Z.
- ISO text có offset +07:00.
- Zoned text có region ID.
- Integer epoch milliseconds.
- Decimal epoch seconds.
- Timestamp có phần nano.
- LocalDateTime không có offset.

Test đọc fixture cũ bằng mapper mới và test writer mới tạo output consumer cũ chấp nhận. Nếu đổi từ timestamp sang ISO text hoặc từ offset-only sang zone-ID string, đó là thay đổi contract cần version hóa hoặc hỗ trợ song song.

Không dùng cùng một mapper cấu hình mới cho cả hai phía trong test tương thích nếu mục tiêu là kiểm tra reader cũ/writer mới. Tạo mapper độc lập theo từng version contract.

## 25. Bộ test mẫu tổng hợp

Một bộ test JUnit nên tổ chức theo nhóm:

~~~java
class JacksonDateTimeTest {
    private final ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
            .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
            .build();

    @Test
    void instantKeepsNanoseconds() throws Exception {
        Instant value =
                Instant.parse("2026-11-12T10:30:00.123456789Z");

        String json = mapper.writeValueAsString(value);
        Instant restored = mapper.readValue(json, Instant.class);

        assertEquals(value, restored);
    }

    @Test
    void offsetDateTimeKeepsOffset() throws Exception {
        OffsetDateTime value =
                OffsetDateTime.parse("2026-11-12T17:30:00.123456789+07:00");

        String json = mapper.writeValueAsString(value);
        OffsetDateTime restored =
                mapper.readValue(json, OffsetDateTime.class);

        assertEquals(value, restored);
        assertEquals(value.getOffset(), restored.getOffset());
    }

    @Test
    void zonedDateTimeKeepsRegion() throws Exception {
        ZoneId zone = ZoneId.of("Europe/Paris");
        ZonedDateTime value = ZonedDateTime.of(
                2026, 7, 1, 12, 0, 0, 123_456_789, zone
        );

        String json = mapper.writeValueAsString(value);
        ZonedDateTime restored =
                mapper.readValue(json, ZonedDateTime.class);

        assertEquals(value, restored);
        assertEquals(zone, restored.getZone());
    }

    @Test
    void localDateTimeDoesNotGainZoneInformation() throws Exception {
        LocalDateTime value =
                LocalDateTime.of(2026, 11, 12, 17, 30, 0, 123_456_789);

        String json = mapper.writeValueAsString(value);
        LocalDateTime restored =
                mapper.readValue(json, LocalDateTime.class);

        assertEquals(value, restored);
    }
}
~~~

Bộ test này là nền tảng. Trong project thực tế, bổ sung parameterized test cho vùng, mùa, DST, timestamp units và precision mà contract hỗ trợ.

## 26. Những lỗi thường gặp khi test ngày giờ

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Instant đúng nhưng offset khác | Mapper điều chỉnh theo context timezone | Kiểm tra ADJUST_DATES_TO_CONTEXT_TIME_ZONE |
| ZonedDateTime mất Europe/Paris | Output chỉ ghi offset, không ghi region ID | Kiểm tra WRITE_DATES_WITH_ZONE_ID và JSON |
| LocalDateTime bị hiểu là giờ UTC | Ứng dụng tự gắn zone mặc định | Kiểm tra logic chuyển đổi ngoài Jackson |
| Timestamp lệch hàng nghìn lần | Nhầm seconds và milliseconds | Kiểm tra READ/WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS |
| Nano bị mất | Dùng epoch millis, Date hoặc database precision thấp hơn | Assert getNano() và kiểm tra tầng lưu trữ |
| Test pass local nhưng fail CI | Phụ thuộc system default timezone/JDK tzdb | Cấu hình zone tường minh và pin runtime |
| DST 02:30 tự đổi thành 03:30 | Local time nằm trong gap | Kiểm tra ZoneRules và chính sách gap |
| Giờ 01:30 không xác định duy nhất | Local time nằm trong overlap | Kiểm tra hai valid offsets |
| Round-trip pass nhưng consumer lỗi | Writer và reader dùng cùng sai quy ước | Thêm contract/interoperability test |
| Date khác LocalDateTime một ngày | Chuyển instant qua timezone gần midnight | Kiểm tra kiểu dữ liệu và vùng hiển thị |

## 27. Quy trình thiết kế test ngày giờ

Khi thêm property ngày giờ vào DTO/API:

1. Xác định dữ liệu là ngày lịch, giờ địa phương, offset, region zone hay instant.
2. Chọn kiểu Java phù hợp: LocalDate, LocalDateTime, OffsetDateTime, ZonedDateTime hoặc Instant.
3. Chốt JSON representation: ISO text, timestamp seconds/milliseconds hay format riêng.
4. Đăng ký JavaTimeModule và cấu hình mapper như production.
5. Quy định có giữ offset/ZoneId hay chuẩn hóa về UTC.
6. Test nhiều vùng, gồm vùng có và không có DST.
7. Test cả DST gap và overlap nếu nghiệp vụ dùng giờ địa phương.
8. Test nano/micro/millisecond và giới hạn của database hoặc hệ thống downstream.
9. Dùng Clock.fixed cho logic phụ thuộc thời điểm hiện tại.
10. Test payload cũ và contract giữa writer/reader version khác nhau.

Đừng dùng một test round-trip duy nhất để đại diện cho mọi kiểu ngày giờ. Mỗi kiểu có invariant riêng.

## 28. Ghi nhớ

Instant là thời điểm tuyệt đối; LocalDateTime chỉ là giờ trên đồng hồ địa phương; OffsetDateTime giữ offset; ZonedDateTime giữ ZoneId cùng quy tắc vùng. Chọn đúng kiểu trước khi chọn serializer.

Với Jackson, đăng ký JavaTimeModule và xác định rõ WRITE_DATES_AS_TIMESTAMPS, WRITE_DATES_WITH_ZONE_ID, WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS, READ_DATE_TIMESTAMPS_AS_NANOSECONDS và ADJUST_DATES_TO_CONTEXT_TIME_ZONE. Test riêng instant, local fields, offset, region ZoneId và phần nano.

Dùng ZoneRules để kiểm tra DST gap/overlap; một local time có thể không tồn tại hoặc xuất hiện hai lần. Dùng Clock.fixed để test thời điểm hiện tại, cấu hình timezone tường minh và tránh trạng thái JVM global. Cuối cùng, kiểm tra cả value round-trip, JSON contract và interoperability với reader độc lập để phát hiện nhầm đơn vị hoặc mất precision.
