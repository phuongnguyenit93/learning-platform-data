# Converting Appointments Between Two Time Zones and Handling DST

## 1. Converting the Same Appointment or Rescheduling?

Suppose an appointment is entered as "02:30 in Berlin". Before displaying it to someone in New York, you must know **which date** it is on and resolve the Berlin time to a specific instant. Then, change the display to New York while keeping the same instant.

The practical flow is:

```text
Local date-time + source zone
    → check for missing/ambiguous time due to DST transition
    → select a valid offset according to policy
    → a resolved instant
    → display the same instant in the target zone
```

Do not convert by adding a fixed difference such as "Berlin is always 6 hours ahead of New York". The two locations may switch to daylight saving time on different dates; the difference also depends on the instant.

## 2. Minimum Input Data

| Component | Example | Role |
| --- | --- | --- |
| `LocalDateTime` | `2025-10-26T02:30` | What the scheduler sees on the local clock |
| Source `ZoneId` | `Europe/Berlin` | Rules for determining the location's offset |
| Overlap choice | Earlier or later occurrence | Selects one instant when two possibilities exist |
| Target `ZoneId` | `America/New_York` | How the recipient views the same appointment |

A `ZoneOffset` like `+02:00` is an offset, not a zone ID. If the input uses a zone name, you must check whether the selected offset is valid for that date-time and zone. If you only receive a time string `02:30` without a date, there is not enough information to handle DST.

## 3. Three Outcomes When Resolving the Source Time

`sourceZone.getRules().getValidOffsets(localDateTime)` returns the valid offsets for the local time:

| Number of offsets | Common meaning | What to do? |
| --- | --- | --- |
| 1 | Normal time | Use that offset |
| 0 | Non-existent time range, called a gap | Reject or adjust according to an explicit policy |
| 2 | Time occurs twice, called an overlap | Choose earlier/later occurrence or ask the user to choose |

In Berlin in 2025, `2025-03-30T02:30` does not exist when the clock springs forward. `2025-10-26T02:30` occurs twice, with `+02:00` and `+01:00`.

For an overlap, the list of offsets is ordered by before and after the transition; choosing `+02:00` in the example gives the earlier instant, while `+01:00` gives the later instant. Do not choose by sorting strings or guessing which offset is "larger". [ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

## 4. Policy for This Exercise

The program below:

- Rejects times that fall in a gap.
- For an overlap, allows the caller to choose `REJECT`, `EARLIER`, or `LATER`.
- After resolving the source time, converts the zone using `withZoneSameInstant`.

`ZonedDateTime.ofStrict(local, offset, zone)` checks whether all three components are compatible. It is suitable when the application already has a specific choice and does not want the library to adjust the time automatically.

`LocalDateTime.atZone(zone)` is convenient but has defaults: it typically pushes a time in a gap forward by the gap duration and picks the earlier offset in an overlap if no other choice is made. Only use that default when it matches the desired contract. [ZonedDateTime: zone resolution](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#ofStrict(java.time.LocalDateTime,java.time.ZoneOffset,java.time.ZoneId))

## 5. Complete Program

Save as `AppointmentZoneDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class AppointmentZoneDemo {
    enum OverlapPolicy { REJECT, EARLIER, LATER }

    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, OverlapPolicy overlapPolicy) {
        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");
        Objects.requireNonNull(overlapPolicy, "overlapPolicy");
        List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException("Local time is in a gap");
        }
        if (offsets.size() == 1) {
            return ZonedDateTime.ofStrict(local, offsets.get(0), zone);
        }
        if (overlapPolicy == OverlapPolicy.REJECT) {
            throw new DateTimeException("Choose an occurrence in the overlap");
        }
        ZoneOffset selected = overlapPolicy == OverlapPolicy.EARLIER
                ? offsets.get(0) : offsets.get(offsets.size() - 1);
        return ZonedDateTime.ofStrict(local, selected, zone);
    }

    public static void main(String[] args) {
        ZoneId source = ZoneId.of("Europe/Berlin");
        ZoneId target = ZoneId.of("America/New_York");
        LocalDateTime overlap = LocalDateTime.of(2025, 10, 26, 2, 30);

        ZonedDateTime earlier = resolve(overlap, source, OverlapPolicy.EARLIER);
        ZonedDateTime later = resolve(overlap, source, OverlapPolicy.LATER);
        ZonedDateTime earlierAtTarget = earlier.withZoneSameInstant(target);

        System.out.println("earlierSource=" + earlier);
        System.out.println("earlierInstant=" + earlier.toInstant());
        System.out.println("earlierTarget=" + earlierAtTarget);
        System.out.println("laterSource=" + later);
        System.out.println("laterInstant=" + later.toInstant());
        System.out.println("laterTarget=" + later.withZoneSameInstant(target));
        System.out.println("occurrenceDistanceMinutes="
                + Duration.between(earlier.toInstant(), later.toInstant()).toMinutes());
        System.out.println("sameInstant="
                + earlier.toInstant().equals(earlierAtTarget.toInstant()));

        ZonedDateTime changedMeaning = earlier.withZoneSameLocal(target);
        System.out.println("sameLocalKeepsInstant="
                + earlier.toInstant().equals(changedMeaning.toInstant()));

        try {
            resolve(overlap, source, OverlapPolicy.REJECT);
        } catch (DateTimeException ex) {
            System.out.println("overlapRejected");
        }

        LocalDateTime gap = LocalDateTime.of(2025, 3, 30, 2, 30);
        try {
            resolve(gap, source, OverlapPolicy.EARLIER);
        } catch (DateTimeException ex) {
            System.out.println("gapRejected");
        }
        System.out.println("defaultGapAdjustment=" + gap.atZone(source));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 AppointmentZoneDemo.java
java AppointmentZoneDemo
```

Stdout with 2025 IANA rules for Berlin/New York:

```text
earlierSource=2025-10-26T02:30+02:00[Europe/Berlin]
earlierInstant=2025-10-26T00:30:00Z
earlierTarget=2025-10-25T20:30-04:00[America/New_York]
laterSource=2025-10-26T02:30+01:00[Europe/Berlin]
laterInstant=2025-10-26T01:30:00Z
laterTarget=2025-10-25T21:30-04:00[America/New_York]
occurrenceDistanceMinutes=60
sameInstant=true
sameLocalKeepsInstant=false
overlapRejected
gapRejected
defaultGapAdjustment=2025-03-30T03:30+02:00[Europe/Berlin]
```

The two choices for 02:30 Berlin are 60 elapsed minutes apart and become two different times on the previous day in New York. Changing the zone can also change the date; never extract only the time part to reconstruct the source date.

`defaultGapAdjustment` demonstrates the library's default behavior, not a branch of the `resolve` method. The method still rejects the non-existent 02:30 input.

## 6. Converting the Same Instant Without Creating New Ambiguity

Once you have an `Instant`, displaying it in the target zone via `instant.atZone(target)` or `withZoneSameInstant(target)` determines a value with an offset. If the target time falls in an overlap, the offset in the result indicates which occurrence it is.

Ambiguity reappears if you drop the offset/zone and keep only the local time string. Therefore, when displaying schedules near a DST transition, include the full date, zone, and/or offset so the recipient interprets it correctly.

`withZoneSameLocal` keeps the local clock reading when changing zones and may change the instant. It is suitable for a different kind of rescheduling, not for changing the view of the same appointment. [ZonedDateTime.withZoneSameInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#withZoneSameInstant(java.time.ZoneId))

## 7. If You Want to Accept Times in a Gap

You can suggest the first valid time after the gap, or shift the entered time forward by the gap duration. These two policies differ: for 02:30 and a 02:00→03:00 gap, choosing the first valid time gives 03:00, whereas shifting by the gap duration gives 03:30.

`ZoneOffsetTransition` provides before/after transition details, `isGap()`, and `getDuration()`. If the application chooses to shift the time, use the actual transition information instead of hardcoding one hour: not every offset change in every zone is 60 minutes long. [ZoneOffsetTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html)

Return the confirmed time to the user so they know the appointment differs from what they originally entered. Do not just save the adjusted result and pretend the user chose it.

## 8. Storing Appointments and Handling Recurrences

For location-based schedules, you can store the entered local date-time, source zone, overlap choice, and resolved instant. Be explicit about which data takes precedence when time zone rules are updated: preserving the local time intent or preserving the confirmed instant.

For a recurring schedule such as "every week at 09:00 Berlin", generate the local date for each occurrence and then resolve it according to the rules. Uniformly adding `Duration.ofDays(7)` to the previous instant does not guarantee keeping 09:00 across a daylight saving time transition.

A meeting finalized as an instant should be sent to participants in a form that unambiguously identifies the same `Instant`; zone information can be included for display. Never send just `02:30` and let each machine attach its default zone.

## 9. Testing Key Scenarios

- Normal time with exactly one offset.
- Time in a gap and each accept/reject policy.
- Both occurrences of an overlap, confirming they have different instants.
- Zone conversion that changes the date on the receiving side.
- A date when the two zones transition at different times.
- Round-trip source→target→source, verifying `toInstant()` is unchanged when the goal is the same appointment.

JDK time zone data is an input to the calculation. When results differ across environments, compare the zone, date-time, offset choice, and rule data before concluding it is merely a formatting bug.

## 10. Self-Practice

1. Change the program's target zone to `Asia/Ho_Chi_Minh` and verify the same `Instant`.
2. For an overlap, try the `REJECT` policy and return a message asking to choose the earlier or later occurrence.
3. Design a response that displays both the entered time and the adjusted time if a gap is accepted.
4. Explain why you do not need to ask the viewer to choose an overlap when the input is already a resolved `Instant`.

Check: (1) changes the view, not the instant; (2) does not guess automatically; (3) clearly shows the change; (4) each instant already determines the offset in the target zone.